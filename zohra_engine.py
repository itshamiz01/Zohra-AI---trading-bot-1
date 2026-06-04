"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA TRADE ENGINE v1.0                           ║
║           Autonomous SMC Trading Agent — MetaTrader 5               ║
║                                                                      ║
║  Runs 24/7. Scans on every new candle. Trades itself.               ║
║  No human input required after launch.                              ║
╚══════════════════════════════════════════════════════════════════════╝

SMC Concepts Implemented:
  ✅ Market Structure  — BOS / CHOCH on H4 + H1
  ✅ Liquidity Sweep   — Equal highs/lows, buy/sell-side sweeps
  ✅ Fair Value Gaps   — Bullish/Bearish FVGs, freshness ranked
  ✅ Order Blocks      — Displacement-confirmed institutional OBs
  ✅ Multi-TF Bias     — Daily → H4 → H1 → M15 cascade
  ✅ Session Filter    — London / NY / Overlap priority
  ✅ Position Manager  — Partial close, BE, structural trail stop
  ✅ Trade Journal     — Full CSV log with SMC reasoning

Launch: python zohra_engine.py
Stop  : Ctrl+C  (graceful shutdown — open trades remain in MT5)
"""

import os, sys, time, csv, signal, math, traceback, json
import datetime as dt
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# ══════════════════════════════════════════════════════════════════════
#  ⚙  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════
SYMBOL              = "XAUUSD"
MAGIC               = 20260604

# Risk
RISK_PCT            = 0.005     # 0.5% equity per trade
DAILY_LOSS_LIMIT    = -1500.0   # Halt day if P&L ≤ -$1500
WEEKLY_LOSS_LIMIT   = -4000.0   # Halt week if P&L ≤ -$4000
MAX_DRAWDOWN_PCT    = 0.03      # Halt if equity drops 3% from start
MAX_DAILY_TRADES    = 15        # Max trades per day (increased for M5 scalping)
MIN_LOT             = 0.01
MAX_LOT             = 5.0       # Increased for tight SL M15 scalps

# SMC thresholds
MIN_SMC_SCORE       = 65        # Min score (0-100) to enter trade
FVG_MIN_SIZE_MULT   = 0.3       # FVG must be ≥ 0.3×ATR to be valid
OB_DISPLACEMENT_MULT= 1.5       # Displacement candle ≥ 1.5×ATR
EQUAL_LEVEL_THRESH  = 0.3       # Equal H/L if within 0.3×ATR

# Position management
PARTIAL_CLOSE_R     = 1.0       # Close 50% at 1R
FULL_CLOSE_R        = 2.0       # Close rest at 2R
BE_TRIGGER_R        = 0.5       # Move to BE when profit = 0.5R
TRAIL_BEHIND_SWING  = True      # Trail SL behind structure swings

# Sessions (UTC)
SESSIONS = {"London": (7,16), "NewYork": (12,21), "Overlap": (13,17)}
HIGH_PRIORITY_SESSIONS = ["Overlap", "London", "NewYork"]

# Scan intervals
SCAN_INTERVAL_SEC   = 15        # Check for new candle every 15s (faster M5 scanning)
MANAGE_INTERVAL_SEC = 15        # Manage open positions every 15s

# Files
LOG_DIR   = os.path.join(os.path.dirname(__file__), "logs")
JOURNAL   = os.path.join(LOG_DIR, "zohra_journal.csv")
SYSLOG    = os.path.join(LOG_DIR, "zohra_engine.log")

# ══════════════════════════════════════════════════════════════════════
#  RUNTIME STATE
# ══════════════════════════════════════════════════════════════════════
STATE = {
    "running":          True,
    "last_h1_candle":   None,
    "session_equity":   0.0,
    "daily_pnl":        0.0,
    "weekly_pnl":       0.0,
    "daily_trades":     0,
    "trading_halted":   False,
    "halt_reason":      "",
    "open_trades":      [],     # list of trade dicts managed by Zohra
    "scan_count":       0,
    "trade_count":      0,
}

# ══════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════
def utc_now():
    return dt.datetime.now(dt.timezone.utc)

def ts():
    return utc_now().strftime("%H:%M:%S")

def datestamp():
    return utc_now().strftime("%Y-%m-%d")

def log(msg, level="INFO"):
    line = f"[{utc_now().strftime('%Y-%m-%d %H:%M:%S')} UTC] [{level}] {msg}"
    print(line)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(SYSLOG, 'a', encoding='utf-8') as f:
        f.write(line + "\n")

def separator(char="─", n=65):
    print(f"  {char*n}")

# ══════════════════════════════════════════════════════════════════════
#  QUANT ENGINE UTILITIES (REGIME & LEARNING)
# ══════════════════════════════════════════════════════════════════════
WEIGHTS_FILE = os.path.join(LOG_DIR, "strategy_weights.json")
REJECTED_LOG = os.path.join(LOG_DIR, "rejected_setups.log")

def load_strategy_weights():
    os.makedirs(LOG_DIR, exist_ok=True)
    defaults = {
        "MarketStructure": 20.0,
        "SMC": 20.0,
        "Trend": 15.0,
        "Momentum": 10.0,
        "Volume": 10.0,
        "Volatility": 10.0,
        "Breakout": 10.0,
        "MeanReversion": 5.0
    }
    if not os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, 'w') as f:
                json.dump(defaults, f, indent=4)
        except: pass
        return defaults
    try:
        with open(WEIGHTS_FILE, 'r') as f:
            w = json.load(f)
            # Ensure all keys exist
            for k in defaults:
                if k not in w: w[k] = defaults[k]
            return w
    except:
        return defaults

def save_strategy_weights(w):
    try:
        # Normalize to sum to 100
        total = sum(w.values())
        if total > 0:
            for k in w:
                w[k] = round((w[k] / total) * 100.0, 2)
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(w, f, indent=4)
    except:
        pass

def update_weights_from_trade(t, pnl):
    mod_perf = t.get('mod_perf')
    if not mod_perf: return
    
    weights = load_strategy_weights()
    win = pnl > 0
    
    for k in weights:
        perf = mod_perf.get(k, 0.0)
        if win:
            if perf >= 0.5:
                weights[k] += 0.5  # Increase weight for contributing module
            else:
                weights[k] -= 0.2  # Decrease weight for non-contributing module
        else:
            if perf >= 0.5:
                weights[k] -= 0.5  # Decrease weight for module that led to loss
            else:
                weights[k] += 0.2  # Increase weight for non-contributing module
                
        # Clamp weight between 2.0 and 35.0
        weights[k] = max(2.0, min(35.0, weights[k]))
        
    save_strategy_weights(weights)
    log(f"🧠 Dynamic weights updated: {weights}")

def detect_market_regime(df):
    if df is None or len(df) < 50:
        return "Ranging"
        
    atr = df['atr'].iloc[-1]
    atr_sma = df['atr'].rolling(20).mean().iloc[-1]
    vol = df['real_volume'].iloc[-1]
    vol_sma = df['vol_sma'].iloc[-1]
    
    # 1. News-Driven (extreme volatility candle body size > 3.0 ATR)
    last_candle_body = df['body'].iloc[-1]
    if last_candle_body > 3.0 * atr:
        return "News-Driven"
        
    # 2. Low Liquidity
    if vol < 0.35 * vol_sma:
        return "Low Liquidity"
        
    # 3. High Volatility Expansion
    if atr > 1.5 * atr_sma:
        return "High Volatility"
        
    # 4. Breakout Check
    close = df['close'].iloc[-1]
    bb_upper = df['bb_upper'].iloc[-1]
    bb_lower = df['bb_lower'].iloc[-1]
    bb_bandwidth = df['bb_bandwidth'].iloc[-1]
    bb_bandwidth_prev = df['bb_bandwidth'].iloc[-5]
    if (close > bb_upper or close < bb_lower) and (bb_bandwidth > bb_bandwidth_prev * 1.25):
        return "Breakout"
        
    # 5. Trending Check (EMA alignment)
    ema20 = df['ema20'].iloc[-1]
    ema50 = df['ema50'].iloc[-1]
    ema200 = df['ema200'].iloc[-1]
    trending_long = close > ema20 > ema50 > ema200
    trending_short = close < ema20 < ema50 < ema200
    if trending_long or trending_short:
        return "Trending"
        
    # 6. Default Regime
    return "Ranging"

def log_rejected_setup(direction, score, mod_perf, reason):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(REJECTED_LOG, 'a', encoding='utf-8') as f:
            f.write(f"\n==================================================\n")
            f.write(f"Trade Rejected - {utc_now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            f.write(f"Symbol: {SYMBOL}\n")
            f.write(f"Direction: {direction}\n")
            f.write(f"Confluence Scores:\n")
            for k, v in mod_perf.items():
                status = "PASS" if v >= 0.5 else "FAIL"
                f.write(f"  • {k}: {status} ({v*100:.0f} pts)\n")
            f.write(f"Final Score: {score}/100\n")
            f.write(f"Final Decision: NO TRADE\n")
            f.write(f"Reason: {reason}\n")
            f.write(f"==================================================\n")
    except:
        pass

def get_filling():
    info = mt5.symbol_info(SYMBOL)
    if info is None: return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 4: return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK

# ══════════════════════════════════════════════════════════════════════
#  DATA FEED
# ══════════════════════════════════════════════════════════════════════
def get_df(tf, count=300):
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    if rates is None or len(rates) < 60:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    # EMAs
    for p in [9, 20, 21, 50, 200]:
        df[f'ema{p}'] = df['close'].ewm(span=p, adjust=False).mean()
    # ATR
    df['tr'] = np.maximum(df['high']-df['low'],
               np.maximum(abs(df['high']-df['close'].shift(1)),
                          abs(df['low'] -df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    # Candle direction
    df['bull'] = df['close'] > df['open']
    df['body'] = abs(df['close'] - df['open'])
    return df

# ══════════════════════════════════════════════════════════════════════
#  MODULE 1 — SESSION FILTER
# ══════════════════════════════════════════════════════════════════════
def current_session():
    h = utc_now().hour
    active = [name for name, (s,e) in SESSIONS.items() if s <= h < e]
    priority = [s for s in active if s in HIGH_PRIORITY_SESSIONS]
    return active, priority

def session_multiplier(priority_sessions):
    """Score multiplier based on session quality."""
    if "Overlap"  in priority_sessions: return 1.0
    if "London"   in priority_sessions: return 0.9
    if "NewYork"  in priority_sessions: return 0.85
    return 0.5   # off-peak — heavy penalty

# ══════════════════════════════════════════════════════════════════════
#  MODULE 2 — MARKET STRUCTURE  (BOS / CHOCH)
# ══════════════════════════════════════════════════════════════════════
def find_swings(df, lookback=50, pivot=3):
    """
    Returns swing highs and lows using n-bar pivot logic.
    A swing high: high[i] is highest of high[i-n:i+n+1]
    A swing low : low[i]  is lowest  of  low[i-n:i+n+1]
    """
    highs, lows = [], []
    subset = df.iloc[-(lookback+pivot*2):-1].reset_index(drop=True)
    n = pivot
    for i in range(n, len(subset)-n):
        window_h = subset['high'].iloc[i-n:i+n+1]
        window_l = subset['low'].iloc[i-n:i+n+1]
        if subset['high'].iloc[i] == window_h.max():
            highs.append({'price': subset['high'].iloc[i],
                          'time':  subset['time'].iloc[i],
                          'idx':   i})
        if subset['low'].iloc[i] == window_l.min():
            lows.append({'price': subset['low'].iloc[i],
                         'time':  subset['time'].iloc[i],
                         'idx':   i})
    return highs, lows

def detect_structure(df_h4, df_h1):
    """
    Returns: bias ('BULL'|'BEAR'|'NEUTRAL'), bos, choch details.
    Uses H4 for major bias, H1 for recent BOS/CHOCH.
    """
    result = {
        "bias":      "NEUTRAL",
        "h4_bull":   False,
        "h1_bull":   False,
        "bos":       None,   # 'BULL_BOS' | 'BEAR_BOS' | None
        "choch":     None,   # 'BULL_CHOCH' | 'BEAR_CHOCH' | None
        "swing_highs_h1": [],
        "swing_lows_h1":  [],
    }

    # ── H4 Bias via EMA ───────────────────────────────────────────
    h4_last  = df_h4.iloc[-1]
    result['h4_bull'] = h4_last['ema20'] > h4_last['ema50']

    # ── H1 Swings ─────────────────────────────────────────────────
    sh_h1, sl_h1 = find_swings(df_h1, lookback=80, pivot=3)
    result['swing_highs_h1'] = sh_h1[-6:] if len(sh_h1) >= 2 else sh_h1
    result['swing_lows_h1']  = sl_h1[-6:] if len(sl_h1) >= 2 else sl_h1

    close_now = df_h1.iloc[-1]['close']

    # ── BOS Detection ─────────────────────────────────────────────
    if len(sh_h1) >= 2:
        last_sh = sh_h1[-2]['price']   # second-to-last swing high
        if close_now > last_sh:
            result['bos']    = 'BULL_BOS'
            result['h1_bull'] = True

    if len(sl_h1) >= 2:
        last_sl = sl_h1[-2]['price']
        if close_now < last_sl:
            result['bos']    = 'BEAR_BOS'
            result['h1_bull'] = False

    # ── CHOCH Detection ───────────────────────────────────────────
    # In a downtrend (lower highs, lower lows), a bullish CHOCH
    # occurs when price breaks above the most recent swing HIGH
    if len(sh_h1) >= 1 and len(sl_h1) >= 2:
        # Check for downtrend: last two swing lows descending
        if sl_h1[-1]['price'] < sl_h1[-2]['price']:
            # Downtrend — watch for bullish CHOCH
            if close_now > sh_h1[-1]['price']:
                result['choch'] = 'BULL_CHOCH'
        # Check for uptrend: last two swing highs ascending
        if len(sh_h1) >= 2 and sh_h1[-1]['price'] > sh_h1[-2]['price']:
            # Uptrend — watch for bearish CHOCH
            if close_now < sl_h1[-1]['price']:
                result['choch'] = 'BEAR_CHOCH'

    # ── Final Bias ────────────────────────────────────────────────
    h4_bull = result['h4_bull']
    h1_bull = result['h1_bull']
    if h4_bull and h1_bull:
        result['bias'] = 'BULL'
    elif not h4_bull and not h1_bull:
        result['bias'] = 'BEAR'
    else:
        result['bias'] = 'NEUTRAL'  # conflicting TFs

    return result

# ══════════════════════════════════════════════════════════════════════
#  MODULE 3 — LIQUIDITY SCANNER
# ══════════════════════════════════════════════════════════════════════
def scan_liquidity(df_h1, atr):
    """
    Find equal highs/lows (liquidity pools) and detect sweeps.
    Returns: buy_side_swept, sell_side_swept, equal_highs, equal_lows
    """
    sh, sl = find_swings(df_h1, lookback=60, pivot=3)
    thresh  = atr * EQUAL_LEVEL_THRESH

    # Equal highs (buy-side liquidity pool)
    equal_highs = []
    for i in range(len(sh)):
        for j in range(i+1, len(sh)):
            if abs(sh[i]['price'] - sh[j]['price']) <= thresh:
                lvl = (sh[i]['price'] + sh[j]['price']) / 2
                equal_highs.append(lvl)

    # Equal lows (sell-side liquidity pool)
    equal_lows = []
    for i in range(len(sl)):
        for j in range(i+1, len(sl)):
            if abs(sl[i]['price'] - sl[j]['price']) <= thresh:
                lvl = (sl[i]['price'] + sl[j]['price']) / 2
                equal_lows.append(lvl)

    # Liquidity sweep detection (last 10 candles)
    recent = df_h1.iloc[-10:]
    price_now  = df_h1.iloc[-1]['close']
    buy_side_swept  = False
    sell_side_swept = False

    # Buy-side sweep: wick above equal high then closed below it
    for lvl in equal_highs:
        wick_above = (recent['high'] > lvl).any()
        close_below= recent.iloc[-1]['close'] < lvl
        if wick_above and close_below:
            buy_side_swept = True
            break

    # Sell-side sweep: wick below equal low then closed above it
    for lvl in equal_lows:
        wick_below = (recent['low'] < lvl).any()
        close_above= recent.iloc[-1]['close'] > lvl
        if wick_below and close_above:
            sell_side_swept = True
            break

    # Also check if latest swing was swept (simple single-level check)
    if sh:
        last_high = sh[-1]['price']
        if (recent['high'] > last_high).any() and price_now < last_high:
            buy_side_swept = True
    if sl:
        last_low = sl[-1]['price']
        if (recent['low'] < last_low).any() and price_now > last_low:
            sell_side_swept = True

    return {
        "buy_side_swept":  buy_side_swept,
        "sell_side_swept": sell_side_swept,
        "equal_highs":     equal_highs,
        "equal_lows":      equal_lows,
        "swing_highs":     sh,
        "swing_lows":      sl,
    }

# ══════════════════════════════════════════════════════════════════════
#  MODULE 4 — FAIR VALUE GAP DETECTOR
# ══════════════════════════════════════════════════════════════════════
def detect_fvgs(df, atr, max_age_candles=30):
    """
    Detect all valid FVGs in the last N candles.
    Bullish FVG: gap between candle[i-1].high and candle[i+1].low
    Bearish FVG: gap between candle[i-1].low and candle[i+1].high
    Returns list of FVG dicts, sorted freshest first.
    """
    fvgs = []
    min_size = atr * FVG_MIN_SIZE_MULT
    subset   = df.iloc[-(max_age_candles+2):-1].reset_index(drop=True)
    n_sub    = len(subset)
    price_now= df.iloc[-1]['close']

    for i in range(1, n_sub - 1):
        c_prev = subset.iloc[i-1]
        c_mid  = subset.iloc[i]
        c_next = subset.iloc[i+1]

        # Bullish FVG
        if c_next['low'] > c_prev['high']:
            size = c_next['low'] - c_prev['high']
            if size >= min_size:
                top    = c_next['low']
                bottom = c_prev['high']
                mid    = (top + bottom) / 2
                # Check if still unfilled (price hasn't re-entered)
                remaining = df.iloc[-(max_age_candles - i):]
                filled = (remaining['low'] <= top).any()
                if not filled or (remaining['low'] <= top).sum() <= 2:
                    fvgs.append({
                        "type":      "BULL",
                        "top":       top,
                        "bottom":    bottom,
                        "mid":       mid,
                        "size":      size,
                        "age":       max_age_candles - i,
                        "candle_time": c_mid['time'],
                        "filled":    filled,
                    })

        # Bearish FVG
        if c_next['high'] < c_prev['low']:
            size = c_prev['low'] - c_next['high']
            if size >= min_size:
                top    = c_prev['low']
                bottom = c_next['high']
                mid    = (top + bottom) / 2
                remaining = df.iloc[-(max_age_candles - i):]
                filled = (remaining['high'] >= bottom).any()
                if not filled or (remaining['high'] >= bottom).sum() <= 2:
                    fvgs.append({
                        "type":      "BEAR",
                        "top":       top,
                        "bottom":    bottom,
                        "mid":       mid,
                        "size":      size,
                        "age":       max_age_candles - i,
                        "candle_time": c_mid['time'],
                        "filled":    filled,
                    })

    # Sort: freshest first, then largest
    fvgs.sort(key=lambda x: (x['age'], -x['size']))
    return fvgs

# ══════════════════════════════════════════════════════════════════════
#  MODULE 5 — ORDER BLOCK DETECTOR
# ══════════════════════════════════════════════════════════════════════
def detect_order_blocks(df, atr, max_age_candles=40):
    """
    Order Block = last opposing candle before a displacement.
    Displacement = candle with body >= 1.5x ATR (institutional move).
    """
    obs = []
    min_displacement = atr * OB_DISPLACEMENT_MULT
    subset = df.iloc[-(max_age_candles+1):-1].reset_index(drop=True)
    price_now = df.iloc[-1]['close']

    for i in range(1, len(subset)):
        c     = subset.iloc[i]
        c_prev= subset.iloc[i-1]
        body  = c['body']

        # Bullish displacement (big green candle)
        if c['bull'] and body >= min_displacement:
            # OB = last bearish candle before this
            for j in range(i-1, max(0, i-5), -1):
                if not subset.iloc[j]['bull']:
                    ob_candle = subset.iloc[j]
                    top    = ob_candle['high']
                    bottom = ob_candle['low']
                    # Check if OB still untested (price hasn't gone back into it)
                    remaining = df.iloc[-(max_age_candles - i):]
                    tested = (remaining['low'] <= top).any() and \
                             (remaining['low'] >= bottom).any()
                    obs.append({
                        "type":    "BULL",
                        "top":     top,
                        "bottom":  bottom,
                        "mid":     (top + bottom) / 2,
                        "age":     max_age_candles - i,
                        "tested":  tested,
                        "displacement": body,
                        "candle_time": ob_candle['time'],
                    })
                    break

        # Bearish displacement (big red candle)
        if not c['bull'] and body >= min_displacement:
            for j in range(i-1, max(0, i-5), -1):
                if subset.iloc[j]['bull']:
                    ob_candle = subset.iloc[j]
                    top    = ob_candle['high']
                    bottom = ob_candle['low']
                    remaining = df.iloc[-(max_age_candles - i):]
                    tested = (remaining['high'] >= bottom).any() and \
                             (remaining['high'] <= top).any()
                    obs.append({
                        "type":    "BEAR",
                        "top":     top,
                        "bottom":  bottom,
                        "mid":     (top + bottom) / 2,
                        "age":     max_age_candles - i,
                        "tested":  tested,
                        "displacement": body,
                        "candle_time": ob_candle['time'],
                    })
                    break

    # Sort: fresh untested first
    obs.sort(key=lambda x: (x['tested'], x['age'], -x['displacement']))
    return obs

# ══════════════════════════════════════════════════════════════════════
#  MODULE 6 — SMC SIGNAL SCORER
# ══════════════════════════════════════════════════════════════════════
def evaluate_signal(struct, liq, fvgs, obs, df_m15, df_m5, atr_m15, session_mult, regime):
    """
    Evaluate LONG and SHORT opportunities using 8 quantitative modules
    weighted adaptively.
    """
    price = df_m15['close'].iloc[-1]
    best  = None
    
    # Load dynamic weights
    weights = load_strategy_weights()
    
    # Apply regime-specific multipliers (Phase 4: Confidence Engine weight adjustment)
    multipliers = {
        "MarketStructure": 1.0,
        "SMC": 1.0,
        "Trend": 1.0,
        "Momentum": 1.0,
        "Volume": 1.0,
        "Volatility": 1.0,
        "Breakout": 1.0,
        "MeanReversion": 1.0
    }
    
    if regime == "Trending":
        multipliers["Trend"] = 1.4
        multipliers["MarketStructure"] = 1.3
        multipliers["MeanReversion"] = 0.3
    elif regime == "Ranging":
        multipliers["MeanReversion"] = 2.5
        multipliers["SMC"] = 1.3
        multipliers["Trend"] = 0.3
    elif regime == "Breakout":
        multipliers["Breakout"] = 2.0
        multipliers["Momentum"] = 1.3
        multipliers["Volume"] = 1.3
        multipliers["Volatility"] = 1.3
        multipliers["Trend"] = 0.5
        multipliers["MeanReversion"] = 0.0
    elif regime == "High Volatility":
        multipliers["Momentum"] = 1.5
        multipliers["Breakout"] = 1.5
        multipliers["Volatility"] = 1.2
        multipliers["Trend"] = 0.5
        multipliers["MeanReversion"] = 0.0
    elif regime == "Low Liquidity":
        # Scaled down to prevent executing trades
        for k in multipliers: multipliers[k] = 0.1
    elif regime == "News-Driven":
        # Blocked entirely
        for k in multipliers: multipliers[k] = 0.0
        
    # Apply multipliers to base weights
    regime_weights = {}
    for k in weights:
        regime_weights[k] = weights[k] * multipliers[k]
        
    # Re-normalize to sum to 100
    w_sum = sum(regime_weights.values())
    if w_sum > 0:
        for k in regime_weights:
            regime_weights[k] = (regime_weights[k] / w_sum) * 100.0
    else:
        for k in regime_weights: regime_weights[k] = 0.0

    for direction in ["LONG", "SHORT"]:
        bull = (direction == "LONG")
        
        # We will collect performance scores (0.0 to 1.0) and details for the 8 modules
        mod_perf = {}
        mod_details = {}

        # ── 1. Market Structure Analysis (Max 20 pts) ────────────────
        bias_ok = (struct['bias'] == 'BULL' and bull) or (struct['bias'] == 'BEAR' and not bull)
        struct_ok = (struct.get('bos') in ['BULL_BOS', 'BEAR_BOS'] and bull == ('BULL' in struct['bos'])) or \
                    (struct.get('choch') in ['BULL_CHOCH', 'BEAR_CHOCH'] and bull == ('BULL' in struct['choch']))
        
        if bias_ok and struct_ok:
            p_struct = 1.0
            desc = f"Bias {struct['bias']} + BOS/CHOCH aligned"
        elif bias_ok:
            p_struct = 0.6
            desc = f"Bias {struct['bias']} aligned (no BOS/CHOCH)"
        elif struct['bias'] == 'NEUTRAL':
            p_struct = 0.3
            desc = "HTF Bias neutral"
        else:
            p_struct = 0.0
            desc = f"HTF Bias {struct['bias']} conflicts"
        mod_perf['MarketStructure'] = p_struct
        mod_details['MarketStructure'] = desc

        # ── 2. Smart Money Concepts (Max 20 pts) ─────────────────────
        # Sweeps
        swept = liq['sell_side_swept'] if bull else liq['buy_side_swept']
        
        # Fresh FVG or OB
        fvg_type = "BULL" if bull else "BEAR"
        valid_fvgs = [f for f in fvgs if f['type'] == fvg_type and not f['filled']]
        near_fvg = None
        if valid_fvgs:
            for f in valid_fvgs[:3]:
                if abs(price - f['mid']) <= atr_m15 * 1.5:
                    near_fvg = f
                    break
                    
        valid_obs = [o for o in obs if o['type'] == fvg_type]
        near_ob = None
        if valid_obs:
            for o in valid_obs[:3]:
                if o['bottom'] <= price <= o['top']:
                    near_ob = o
                    break
        
        # Premium / Discount Zone
        # Find high/low of last 40 candles
        recent_candles = df_m15.iloc[-40:]
        highest_high = recent_candles['high'].max()
        lowest_low = recent_candles['low'].min()
        rng = highest_high - lowest_low
        p_pct = (price - lowest_low) / (rng + 1e-9)
        zone_ok = p_pct <= 0.5 if bull else p_pct >= 0.5
        
        p_smc = 0.0
        smc_reasons = []
        if swept:
            p_smc += 0.4
            smc_reasons.append("Sweep")
        if near_fvg or near_ob:
            p_smc += 0.4
            smc_reasons.append("FVG/OB Tap")
        elif valid_fvgs or valid_obs:
            p_smc += 0.1
            smc_reasons.append("FVG/OB Exist")
        if zone_ok:
            p_smc += 0.2
            smc_reasons.append("Discount" if bull else "Premium")
            
        mod_perf['SMC'] = p_smc
        mod_details['SMC'] = "+".join(smc_reasons) if smc_reasons else "No SMC setups"

        # ── 3. Trend Analysis (Max 15 pts) ───────────────────────────
        ema20 = df_m15['ema20'].iloc[-1]
        ema50 = df_m15['ema50'].iloc[-1]
        
        # M15 Trend
        m15_trend_ok = (price > ema20 > ema50) if bull else (price < ema20 < ema50)
        
        # MTF Trend: check H1 Trend (passed as struct['h4_bull'] inside evaluate_signal)
        h1_trend_ok = struct['h4_bull'] if bull else not struct['h4_bull']
        
        p_trend = 0.0
        trend_reasons = []
        if m15_trend_ok:
            p_trend += 0.6
            trend_reasons.append("M15 aligned")
        if h1_trend_ok:
            p_trend += 0.4
            trend_reasons.append("H1 aligned")
            
        mod_perf['Trend'] = p_trend
        mod_details['Trend'] = "+".join(trend_reasons) if trend_reasons else "Counter-trend"

        # ── 4. Momentum Analysis (Max 10 pts) ────────────────────────
        rsi = df_m15['rsi'].iloc[-1]
        rsi_prev = df_m15['rsi'].iloc[-2]
        macd = df_m15['macd'].iloc[-1]
        macd_signal = df_m15['macd_signal'].iloc[-1]
        
        rsi_ok = (rsi > 50 and rsi > rsi_prev) if bull else (rsi < 50 and rsi < rsi_prev)
        macd_ok = (macd > macd_signal) if bull else (macd < macd_signal)
        
        p_mom = (0.5 if rsi_ok else 0.0) + (0.5 if macd_ok else 0.0)
        mod_perf['Momentum'] = p_mom
        mod_details['Momentum'] = f"RSI={rsi:.1f} MACD={'OK' if macd_ok else 'NO'}"

        # ── 5. Volume Analysis (Max 10 pts) ──────────────────────────
        vol = df_m15['real_volume'].iloc[-1]
        vol_sma = df_m15['vol_sma'].iloc[-1]
        rvol = vol / (vol_sma + 1e-9)
        
        vol_spike = vol > vol_sma
        rvol_ok = rvol > 1.2
        
        p_vol = (0.5 if vol_spike else 0.0) + (0.5 if rvol_ok else 0.0)
        mod_perf['Volume'] = p_vol
        mod_details['Volume'] = f"RVol={rvol:.2f}"

        # ── 6. Volatility Analysis (Max 10 pts) ──────────────────────
        atr = df_m15['atr'].iloc[-1]
        atr_prev = df_m15['atr'].iloc[-2]
        bb_bandwidth = df_m15['bb_bandwidth'].iloc[-1]
        bb_bandwidth_prev = df_m15['bb_bandwidth'].iloc[-2]
        
        atr_expanding = atr > atr_prev
        bb_expanding = bb_bandwidth > bb_bandwidth_prev
        
        p_volat = (0.5 if atr_expanding else 0.1) + (0.5 if bb_expanding else 0.1)
        mod_perf['Volatility'] = p_volat
        mod_details['Volatility'] = f"ATR={atr:.2f} BBWidth={bb_bandwidth:.3f}"

        # ── 7. Breakout Analysis (Max 10 pts) ────────────────────────
        prev_15 = df_m15.iloc[-18:-3]
        max_prev_15 = prev_15['high'].max()
        min_prev_15 = prev_15['low'].min()
        
        breakout = (price > max_prev_15) if bull else (price < min_prev_15)
        bb_break = (price > df_m15['bb_upper'].iloc[-1]) if bull else (price < df_m15['bb_lower'].iloc[-1])
        
        p_break = 1.0 if (breakout or bb_break) else 0.0
        mod_perf['Breakout'] = p_break
        mod_details['Breakout'] = "Breakout confirmed" if p_break > 0 else "Range bound"

        # ── 8. Mean Reversion Analysis (Max 5 pts) ───────────────────
        near_ema = abs(price - ema20) <= atr * 1.2
        extrema = (rsi < 30) if bull else (rsi > 70)
        
        p_rev = 1.0 if (near_ema or extrema) else 0.3
        mod_perf['MeanReversion'] = p_rev
        mod_details['MeanReversion'] = "Value entry" if near_ema else "Extreme RSI" if extrema else "Stretched"

        # ── Score calculation ────────────────────────────────────────
        weighted_score = 0.0
        reasons = []
        for k in regime_weights:
            contrib = regime_weights[k] * mod_perf[k]
            weighted_score += contrib
            reasons.append(f"{k}: {contrib:.1f}/{regime_weights[k]:.1f} ({mod_details[k]})")

        # Session multiplier penalty
        final_score = int(weighted_score * session_mult)
        
        # Stop loss logic (same ATR bounds as before)
        si = mt5.symbol_info(SYMBOL)
        point = si.point
        buf = 40 * point
        
        if bull:
            if valid_obs and near_ob:
                sl = round(near_ob['bottom'] - buf, si.digits)
            elif liq['swing_lows']:
                sl = round(liq['swing_lows'][-1]['price'] - buf, si.digits)
            else:
                sl = round(price - atr_m15 * 1.5, si.digits)
            if price - sl > atr_m15 * 3: sl = round(price - atr_m15 * 2.5, si.digits)
            if price - sl < atr_m15 * 0.5: sl = round(price - atr_m15 * 0.8, si.digits)
            entry_zone = (price, price + atr_m15 * 0.2)
        else:
            if valid_obs and near_ob:
                sl = round(near_ob['top'] + buf, si.digits)
            elif liq['swing_highs']:
                sl = round(liq['swing_highs'][-1]['price'] + buf, si.digits)
            else:
                sl = round(price + atr_m15 * 1.5, si.digits)
            if sl - price > atr_m15 * 3: sl = round(price + atr_m15 * 2.5, si.digits)
            if sl - price < atr_m15 * 0.5: sl = round(price + atr_m15 * 0.8, si.digits)
            entry_zone = (price - atr_m15 * 0.2, price)

        # We collect the candidate regardless of score (if score >= 30, so we avoid logging garbage with 0 score)
        if final_score >= 30:
            candidate = {
                "direction":   direction,
                "score":       final_score,
                "entry_zone":  entry_zone,
                "sl":          sl,
                "reasons":     reasons,
                "skips":       [],
                "near_fvg":    near_fvg,
                "near_ob":     near_ob,
                "liq_swept":   swept,
                "mod_perf":    mod_perf,  # Store performance scores for learning update
                "regime":      regime,
            }
            if best is None or final_score > best['score']:
                best = candidate

    return best

# ══════════════════════════════════════════════════════════════════════
#  MODULE 7 — RISK ENGINE
# ══════════════════════════════════════════════════════════════════════
def calc_position(equity, sl_price, entry_price):
    """Returns lots, risk_usd. XAUUSD: $1/pt/lot."""
    sl_pts   = abs(entry_price - sl_price) / 0.01   # convert to points
    risk_usd = equity * RISK_PCT
    lots     = risk_usd / (sl_pts * 1.0)
    lots     = max(MIN_LOT, min(MAX_LOT,
               round(round(lots / mt5.symbol_info(SYMBOL).volume_step)
                     * mt5.symbol_info(SYMBOL).volume_step, 2)))
    actual_risk = sl_pts * lots
    return lots, actual_risk

def check_risk_limits(equity, start_equity):
    """Returns (allowed, reason)."""
    if STATE['trading_halted']:
        return False, STATE['halt_reason']
    if STATE['daily_pnl'] <= DAILY_LOSS_LIMIT:
        msg = f"Daily loss limit hit (${STATE['daily_pnl']:.2f})"
        STATE['trading_halted'] = True; STATE['halt_reason'] = msg
        return False, msg
    if STATE['weekly_pnl'] <= WEEKLY_LOSS_LIMIT:
        msg = f"Weekly loss limit hit (${STATE['weekly_pnl']:.2f})"
        STATE['trading_halted'] = True; STATE['halt_reason'] = msg
        return False, msg
    dd_pct = (equity - start_equity) / start_equity if start_equity > 0 else 0
    if dd_pct <= -MAX_DRAWDOWN_PCT:
        msg = f"Max drawdown hit ({dd_pct*100:.1f}%)"
        STATE['trading_halted'] = True; STATE['halt_reason'] = msg
        return False, msg
    if STATE['daily_trades'] >= MAX_DAILY_TRADES:
        return False, f"Max daily trades ({MAX_DAILY_TRADES}) reached"
    return True, "OK"

# ══════════════════════════════════════════════════════════════════════
#  MODULE 8 — ORDER EXECUTION
# ══════════════════════════════════════════════════════════════════════
def place_order(signal, lots, equity):
    si    = mt5.symbol_info(SYMBOL)
    tick  = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        log("Cannot get tick data", "ERROR"); return None

    direction = signal['direction']
    sl_price  = signal['sl']
    otype     = mt5.ORDER_TYPE_BUY  if direction == "LONG" else mt5.ORDER_TYPE_SELL
    price     = tick.ask             if direction == "LONG" else tick.bid
    sl_dist   = abs(price - sl_price)

    # TP at 2R from entry
    tp2_price = round(price + sl_dist * FULL_CLOSE_R, si.digits) \
                if direction == "LONG" else \
                round(price - sl_dist * FULL_CLOSE_R, si.digits)

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       lots,
        "type":         otype,
        "price":        price,
        "sl":           round(sl_price, si.digits),
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"Zohra_SMC_{signal['score']}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(),
    }
    r = mt5.order_send(req)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        err = r.comment if r else str(mt5.last_error())
        log(f"Order FAILED: {err}", "ERROR")
        return None

    fill = r.price if r.price else price
    tp1  = round(fill + sl_dist * PARTIAL_CLOSE_R, si.digits) \
           if direction == "LONG" else \
           round(fill - sl_dist * PARTIAL_CLOSE_R, si.digits)
    tp2  = round(fill + sl_dist * FULL_CLOSE_R, si.digits) \
           if direction == "LONG" else \
           round(fill - sl_dist * FULL_CLOSE_R, si.digits)

    trade = {
        "ticket":        r.order,
        "direction":     direction,
        "entry":         fill,
        "sl":            sl_price,
        "sl_dist":       sl_dist,
        "tp1":           tp1,
        "tp2":           tp2,
        "lots":          lots,
        "lots_orig":     lots,
        "be_set":        False,
        "partial_done":  False,
        "trail_sl":      sl_price,
        "closed":        False,
        "open_time":     utc_now().isoformat(),
        "score":         signal['score'],
        "liq_swept":     signal['liq_swept'],
        "has_fvg":       signal['near_fvg'] is not None,
        "has_ob":        signal['near_ob']  is not None,
        "peak_pnl":      0.0,
        "mod_perf":      signal.get('mod_perf', {}),  # Added for adaptive learning
        "regime":        signal.get('regime', 'Ranging'),  # Added for regime classification
    }

    STATE['daily_trades'] += 1
    STATE['trade_count']  += 1
    return trade

def close_position(t, volume=None, reason=""):
    pos_list = mt5.positions_get(ticket=t['ticket'])
    if not pos_list: return True, 0.0
    pos   = pos_list[0]
    vol   = volume or pos.volume
    tick  = mt5.symbol_info_tick(SYMBOL)
    si    = mt5.symbol_info(SYMBOL)
    ctype = mt5.ORDER_TYPE_SELL if t['direction'] == "LONG" else mt5.ORDER_TYPE_BUY
    price = tick.bid             if t['direction'] == "LONG" else tick.ask
    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       round(vol, 2),
        "type":         ctype,
        "position":     t['ticket'],
        "price":        price,
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"Z_Close_{reason}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(),
    }
    r = mt5.order_send(req)
    ok  = r is not None and r.retcode == mt5.TRADE_RETCODE_DONE
    pnl = pos.profit * (vol / pos.volume) if ok else 0.0
    return ok, pnl

def update_sl(t, new_sl):
    pos_list = mt5.positions_get(ticket=t['ticket'])
    if not pos_list: return False
    pos = pos_list[0]
    si  = mt5.symbol_info(SYMBOL)
    req = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   SYMBOL,
        "position": t['ticket'],
        "sl":       round(new_sl, si.digits),
        "tp":       pos.tp,
    }
    r = mt5.order_send(req)
    return r is not None and r.retcode == mt5.TRADE_RETCODE_DONE

# ══════════════════════════════════════════════════════════════════════
#  MODULE 9 — POSITION MANAGER
# ══════════════════════════════════════════════════════════════════════
def manage_all_positions(df_h1):
    """Called every 30s. Manages all Zohra-opened trades."""
    si         = mt5.symbol_info(SYMBOL)
    point      = si.point
    sh, sl_sw  = find_swings(df_h1, lookback=20, pivot=2)

    for t in [x for x in STATE['open_trades'] if not x['closed']]:
        pos_list = mt5.positions_get(ticket=t['ticket'])

        if not pos_list:
            # Closed by MT5 (SL/TP hit)
            t['closed'] = True
            pnl = 0.0
            try:
                now_utc_naive = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                deals = mt5.history_deals_get(
                    now_utc_naive - dt.timedelta(minutes=60),
                    now_utc_naive + dt.timedelta(minutes=1),
                )
                if deals:
                    for d in deals:
                        if d.position_id == t['ticket'] and d.profit != 0:
                            pnl += d.profit
            except: pass
            log(f"Position {t['ticket']} closed by MT5 | P&L ${pnl:+.2f}")
            journal_trade(t, pnl, "MT5_AUTO")
            STATE['daily_pnl']  += pnl
            STATE['weekly_pnl'] += pnl
            continue

        pos    = pos_list[0]
        pnl    = pos.profit
        t['peak_pnl'] = max(t.get('peak_pnl', 0.0), pnl)
        sl_r   = t['sl_dist'] * t['lots'] * 100  # $1/pt/lot × pts × lots
        r_mult = pnl / sl_r if sl_r > 0 else 0

        bull = t['direction'] == "LONG"

        # ── Partial close at 1R ───────────────────────────────────
        if not t['partial_done'] and r_mult >= PARTIAL_CLOSE_R:
            half = round(t['lots'] / 2, 2)
            half = max(si.volume_min, half)
            ok, part_pnl = close_position(t, volume=half, reason="PARTIAL_1R")
            if ok:
                t['partial_done'] = True
                t['lots']        -= half
                log(f"  ✅ PARTIAL CLOSE {t['ticket']} 50% @ 1R | P&L ${part_pnl:+.2f}")
                # Move SL to breakeven
                ok2 = update_sl(t, t['entry'])
                if ok2:
                    t['be_set']   = True
                    t['trail_sl'] = t['entry']
                    log(f"  ⚡ BE SET @ ${t['entry']:.2f}")
                STATE['daily_pnl']  += part_pnl
                STATE['weekly_pnl'] += part_pnl

        # ── Full close at 2R ──────────────────────────────────────
        elif t['partial_done'] and r_mult >= FULL_CLOSE_R:
            ok, final_pnl = close_position(t, reason="FULL_2R")
            t['closed'] = True
            log(f"  🏆 FULL CLOSE {t['ticket']} @ 2R | P&L ${final_pnl:+.2f}")
            journal_trade(t, final_pnl, "FULL_2R")
            STATE['daily_pnl']  += final_pnl
            STATE['weekly_pnl'] += final_pnl

        # ── Trail SL behind recent swing ─────────────────────────
        elif t['be_set'] and TRAIL_BEHIND_SWING and pnl > 0:
            tick_now = mt5.symbol_info_tick(SYMBOL)
            if bull and sh:
                # Trail behind last swing low
                if sl_sw:
                    last_sl_price = sl_sw[-1]['price']
                    new_trail = round(last_sl_price - 20*point, si.digits)
                    if new_trail > t['trail_sl'] + point * 10:
                        ok = update_sl(t, new_trail)
                        if ok:
                            t['trail_sl'] = new_trail
                            log(f"  📈 TRAIL SL {t['ticket']} → ${new_trail:.2f}")
            elif not bull and sl_sw:
                last_sh_price = sh[-1]['price'] if sh else 0
                new_trail = round(last_sh_price + 20*point, si.digits)
                if new_trail < t['trail_sl'] - point * 10:
                    ok = update_sl(t, new_trail)
                    if ok:
                        t['trail_sl'] = new_trail
                        log(f"  📉 TRAIL SL {t['ticket']} → ${new_trail:.2f}")

        # ── Structure invalidation check ──────────────────────────
        # If thesis invalidated (price broke structure against us), exit
        elif not t['be_set'] and r_mult <= -0.75:
            ok, pnl_exit = close_position(t, reason="THESIS_INVALID")
            t['closed'] = True
            log(f"  ⚠️  THESIS INVALID {t['ticket']} | P&L ${pnl_exit:+.2f}")
            journal_trade(t, pnl_exit, "THESIS_INVALID")
            STATE['daily_pnl']  += pnl_exit
            STATE['weekly_pnl'] += pnl_exit

# ══════════════════════════════════════════════════════════════════════
#  MODULE 10 — TRADE JOURNAL
# ══════════════════════════════════════════════════════════════════════
def init_journal():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(JOURNAL):
        with open(JOURNAL, 'w', newline='') as f:
            csv.writer(f).writerow([
                "date", "ticket", "symbol", "regime", "strategy_type",
                "score", "entry", "sl", "tp1", "tp2", "exit_price",
                "pnl_usd", "r_multiple", "exit_reason", "session",
                "market_conditions", "open_time"
            ])

def journal_trade(t, pnl, reason):
    if reason != "OPEN":
        update_weights_from_trade(t, pnl)

    sl_r    = t['sl_dist'] * t['lots_orig'] * 100
    r_mult  = round(pnl / sl_r, 2) if sl_r > 0 else 0
    _, sess = current_session()
    
    conds = f"Score={t['score']};OB={t['has_ob']};FVG={t['has_fvg']}"
    exit_price = round(t['entry'] + (pnl / (t['lots_orig'] * 100)), 2) if reason != "OPEN" else 0.0
    
    with open(JOURNAL, 'a', newline='') as f:
        csv.writer(f).writerow([
            datestamp(), t['ticket'], SYMBOL, t.get('regime', 'Ranging'), "Quant_SMC",
            t['score'], f"{t['entry']:.2f}", f"{t['sl']:.2f}", f"{t['tp1']:.2f}", f"{t['tp2']:.2f}",
            f"{exit_price:.2f}", f"{pnl:.2f}", f"{r_mult:.2f}",
            reason, ','.join(sess) or 'off-peak', conds, t['open_time']
        ])

def print_stats():
    try:
        df_j = pd.read_csv(JOURNAL)
        df_closed = df_j[df_j['exit_reason'] != 'OPEN']
        if len(df_closed) == 0: return
        pnl_vals = df_closed['pnl_usd'].astype(float).tolist()
        total   = len(df_closed)
        wins    = (df_closed['pnl_usd'].astype(float) > 0).sum()
        losses  = total - wins
        tot_pnl = sum(pnl_vals)
        avg_rr  = df_closed['r_multiple'].astype(float).mean()
        
        win_pnl = df_closed[df_closed['pnl_usd'].astype(float) > 0]['pnl_usd'].astype(float).sum()
        loss_pnl = df_closed[df_closed['pnl_usd'].astype(float) <= 0]['pnl_usd'].astype(float).sum()
        
        profit_factor = win_pnl / abs(loss_pnl) if loss_pnl != 0 else float('inf') if win_pnl > 0 else 0.0
        
        avg_win = df_closed[df_closed['pnl_usd'].astype(float) > 0]['pnl_usd'].astype(float).mean() if wins else 0
        avg_loss= df_closed[df_closed['pnl_usd'].astype(float) <= 0]['pnl_usd'].astype(float).mean() if losses else 0
        
        win_rate = wins / total
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        
        cum_pnl = np.cumsum(pnl_vals)
        running_max = np.maximum.accumulate(cum_pnl)
        drawdowns = running_max - cum_pnl
        max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
        
        w = load_strategy_weights()

        print(f"\n  ── Zohra Quant Engine Performance Stats ───────────────")
        print(f"  Trades  : {total}  |  Wins: {wins}  |  Losses: {losses}")
        print(f"  Win Rate: {win_rate*100:.1f}%  |  Avg R/R: {avg_rr:.2f}")
        print(f"  Avg Win : ${avg_win:.2f}  |  Avg Loss: ${avg_loss:.2f}")
        print(f"  Profit Factor: {profit_factor:.2f}  |  Expectancy: ${expectancy:.2f}")
        print(f"  Max realized drawdown: ${max_dd:.2f}")
        print(f"  Total realized P&L: ${tot_pnl:+.2f}")
        print(f"  ── Current Strategy Weights ─────────────────────────────")
        for k, v in w.items():
            print(f"    • {k}: {v:.1f}%")
        print(f"  ═════════════════════════════════════════════════════════")
    except Exception as e:
        print(f"Error calculating stats: {e}")

# ══════════════════════════════════════════════════════════════════════
#  CORE SCAN CYCLE
# ══════════════════════════════════════════════════════════════════════
def run_scan_cycle():
    """One full SMC analysis + trade decision cycle."""
    STATE['scan_count'] += 1

    # ── Fetch data ────────────────────────────────────────────────
    df_h1  = get_df(mt5.TIMEFRAME_H1,  150)
    df_m15 = get_df(mt5.TIMEFRAME_M15, 250)
    df_m5  = get_df(mt5.TIMEFRAME_M5,  150)

    if any(d is None for d in [df_h1, df_m15]):
        log("Data fetch failed — skipping cycle", "WARN")
        return

    # ── Phase 1: Market Regime Detection ──────────────────────────
    regime = detect_market_regime(df_m15)
    log(f"Market Regime classified: {regime.upper()} | Running scans...")

    atr_m15 = df_m15['atr'].iloc[-1]
    price  = df_m15['close'].iloc[-1]

    # ── SMC Analysis ─────────────────────────────────────────────
    # Use H1 for Higher TF bias, M15 for execution structure
    struct = detect_structure(df_h1, df_m15)
    liq    = scan_liquidity(df_m15, atr_m15)
    fvgs   = detect_fvgs(df_m15, atr_m15, max_age_candles=30)
    obs    = detect_order_blocks(df_m15, atr_m15, max_age_candles=40)

    # ── Session ───────────────────────────────────────────────────
    active_sess, priority_sess = current_session()
    s_mult = session_multiplier(priority_sess)

    # ── Signal Evaluation ─────────────────────────────────────────
    # df_m15 is execution TF, df_m5 is confirmation TF, atr_m15 is ATR
    signal = evaluate_signal(struct, liq, fvgs, obs,
                              df_m15, df_m5, atr_m15, s_mult, regime)

    # ── Check risk limits ─────────────────────────────────────────
    acc = mt5.account_info()
    if acc is None:
        log("Cannot get account info", "WARN"); return
    equity = acc.equity

    can_trade, limit_reason = check_risk_limits(equity, STATE['session_equity'])

    # ── No signal at all ──────────────────────────────────────────
    if signal is None:
        bias_str  = struct['bias']
        bos_str   = struct.get('bos',   'None')
        choch_str = struct.get('choch', 'None')
        sess_str  = ','.join(priority_sess) if priority_sess else 'off-peak'
        log(f"Monitoring | Price ${price:.2f} | Bias {bias_str} | "
            f"BOS {bos_str} | CHOCH {choch_str} | Session {sess_str} | "
            f"FVGs {len(fvgs)} OBs {len(obs)} | "
            f"No setup detected (scan #{STATE['scan_count']})")
        return

    # ── Check execution score thresholds ──────────────────────────
    score = signal['score']
    
    # 0-60: Reject setup
    if score <= 60:
        log(f"Setup Rejected | {signal['direction']} score={score}/100 — below minimum threshold (60)")
        log_rejected_setup(signal['direction'], score, signal['mod_perf'], "Score below minimum execution threshold (60)")
        return
        
    # 61-75: Monitor only
    if 61 <= score <= 75:
        log(f"👀 MONITOR SETUP: {signal['direction']} score={score}/100 — Monitor only, no trade placed.")
        print(f"\n  👀 MODULE CONFLUENCE SCORES:")
        for r in signal['reasons']: print(f"     {r}")
        log_rejected_setup(signal['direction'], score, signal['mod_perf'], "Monitor only range (61-75)")
        return

    # ── Signal is valid for execution (score >= 76) ───────────────
    # Check if already in this direction
    open_dirs = [t['direction'] for t in STATE['open_trades']
                 if not t['closed']]
    if signal['direction'] in open_dirs:
        log(f"Signal {signal['direction']} found (score={score}) "
            f"but already have open {signal['direction']} position — skip")
        log_rejected_setup(signal['direction'], score, signal['mod_perf'], f"Already in open {signal['direction']} position")
        return

    if not can_trade:
        log(f"Signal {signal['direction']} score={score} — "
            f"BLOCKED: {limit_reason}", "WARN")
        log_rejected_setup(signal['direction'], score, signal['mod_perf'], f"Blocked by risk limit: {limit_reason}")
        return

    # ── Execute trade (score >= 76) ───────────────────────────────
    entry_price = (signal['entry_zone'][0] + signal['entry_zone'][1]) / 2
    lots, risk_usd = calc_position(equity, signal['sl'], entry_price)

    # Position sizing adjustment: 76-85 is reduced-risk (50% size)
    is_small = 76 <= score <= 85
    if is_small:
        lots = round(lots * 0.5, 2)
        lots = max(MIN_LOT, lots)
        risk_usd = risk_usd * 0.5

    size_label = "SMALL POSITION (REDUCED RISK)" if is_small else "FULL POSITION (FULL RISK)"

    separator("═")
    log(f"🎯 QUANT SIGNAL DETECTED ({size_label}) — {signal['direction']} XAUUSD")
    log(f"   Regime     : {regime}")
    log(f"   Score      : {score}/100")
    log(f"   Price      : ${price:.2f}")
    log(f"   Stop Loss  : ${signal['sl']:.2f}")
    log(f"   Lots       : {lots}  Risk: ${risk_usd:.2f}")
    log(f"   Session    : {','.join(priority_sess) or 'off-peak'}")
    print(f"\n  ✅ MODULE CONFLUENCE DETAILS:")
    for r in signal['reasons']: print(f"     {r}")
    separator()

    trade = place_order(signal, lots, equity)
    if trade:
        # Add regime to trade dictionary
        trade['regime'] = regime
        STATE['open_trades'].append(trade)
        log(f"✅ TRADE OPENED | Ticket {trade['ticket']} | "
            f"{trade['direction']} @ ${trade['entry']:.2f} | "
            f"SL ${trade['sl']:.2f} | Lots {lots}")
        journal_trade(trade, 0, "OPEN")  # log entry
    else:
        log("Order execution failed", "ERROR")

# ══════════════════════════════════════════════════════════════════════
#  GRACEFUL SHUTDOWN
# ══════════════════════════════════════════════════════════════════════
def shutdown(sig=None, frame=None):
    print("\n")
    separator("═")
    log("🛑 ZOHRA ENGINE SHUTTING DOWN — Ctrl+C received")
    log("   Open trades remain active in MT5 with SL/TP set.")
    log(f"   Session P&L  : ${STATE['daily_pnl']:+.2f}")
    log(f"   Total scans  : {STATE['scan_count']}")
    log(f"   Total trades : {STATE['trade_count']}")
    print_stats()
    separator("═")
    STATE['running'] = False
    try: mt5.shutdown()
    except: pass
    sys.exit(0)

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ══════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════
print("\n" + "═"*67)
print("  ╔══════════════════════════════════════════════════════════╗")
print("  ║          ZOHRA TRADE ENGINE  v1.0                       ║")
print("  ║   Autonomous SMC Agent — XAUUSD — MetaTrader 5          ║")
print("  ╚══════════════════════════════════════════════════════════╝")
print("═"*67)
print(f"  Risk/trade    : {RISK_PCT*100:.1f}%  |  Min score: {MIN_SMC_SCORE}/100")
print(f"  Daily halt    : ${DAILY_LOSS_LIMIT}  |  Weekly halt: ${WEEKLY_LOSS_LIMIT}")
print(f"  Partial @     : {PARTIAL_CLOSE_R}R   |  Full exit @ {FULL_CLOSE_R}R")
print(f"  Max trades/day: {MAX_DAILY_TRADES}")
print(f"  Scan interval : {SCAN_INTERVAL_SEC}s  (new H1 candle detected)")
print(f"  Stop          : Ctrl+C  (trades stay open in MT5)")
print("═"*67)

# Connect to MT5
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}"); sys.exit(1)
if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
    print(f"Login failed: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

acc = mt5.account_info()
STATE['session_equity'] = acc.equity
print(f"\n  ✅ MT5 Connected | {acc.name} | Balance: ${acc.balance:,.2f} | "
      f"Equity: ${acc.equity:,.2f}")

if not mt5.symbol_select(SYMBOL, True):
    print(f"  {SYMBOL} not available!"); mt5.shutdown(); sys.exit(1)

init_journal()
log(f"Zohra Engine started | Equity ${acc.equity:,.2f}")

# ══════════════════════════════════════════════════════════════════════
#  MAIN LOOP — runs forever until Ctrl+C
# ══════════════════════════════════════════════════════════════════════
print(f"\n  🤖 Zohra is now monitoring {SYMBOL} autonomously...")
print(f"  Scanning every {SCAN_INTERVAL_SEC}s. Press Ctrl+C to stop.\n")

last_manage_time = 0.0
last_scan_time   = 0.0
last_heartbeat_time = 0.0
last_bar_time    = None  # timestamp of last known candle (M5)

while STATE['running']:
    try:
        now_ts = time.time()

        # ── Manage open positions every 15s ───────────────────────
        if now_ts - last_manage_time >= MANAGE_INTERVAL_SEC:
            open_count = sum(1 for t in STATE['open_trades'] if not t['closed'])
            if open_count > 0:
                df_m15 = get_df(mt5.TIMEFRAME_M15, 50)
                if df_m15 is not None:
                    manage_all_positions(df_m15)
            last_manage_time = now_ts

        # ── Scan for new M5 candle every 15s ──────────────────────
        if now_ts - last_scan_time >= SCAN_INTERVAL_SEC:
            rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 2)
            if rates is not None and len(rates) >= 2:
                latest_candle_time = rates[-1]['time']  # last closed candle

                if last_bar_time is None or latest_candle_time != last_bar_time:
                    last_bar_time = latest_candle_time
                    ct = dt.datetime.fromtimestamp(latest_candle_time,
                             tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
                    log(f"New M5 candle → {ct} UTC | Running SMC scan...")
                    run_scan_cycle()
                else:
                    # No new candle — just show heartbeat every 5 min
                    if now_ts - last_heartbeat_time >= 300:
                        open_n = sum(1 for t in STATE['open_trades'] if not t['closed'])
                        log(f"♥ Heartbeat | Price ${rates[-1]['close']:.2f} | "
                            f"Open positions: {open_n} | "
                            f"Day P&L: ${STATE['daily_pnl']:+.2f}")
                        last_heartbeat_time = now_ts

            last_scan_time = now_ts

        # ── Auto-reset daily stats at 21:00 UTC ───────────────────
        if utc_now().hour == 21 and utc_now().minute == 0:
            log(f"Daily reset | Day P&L was ${STATE['daily_pnl']:+.2f}")
            STATE['daily_pnl']   = 0.0
            STATE['daily_trades']= 0
            if STATE['trading_halted'] and 'daily' in STATE['halt_reason'].lower():
                STATE['trading_halted'] = False
                STATE['halt_reason']    = ""
                log("Daily halt cleared — trading resumed for new day")

        time.sleep(5)   # 5s tick — tight enough for position management

    except KeyboardInterrupt:
        shutdown()

    except Exception as e:
        log(f"LOOP ERROR: {str(e)}\n{traceback.format_exc()}", "ERROR")
        time.sleep(30)  # Back off on error, then continue
        # Auto-reconnect
        try:
            if not mt5.account_info():
                log("MT5 disconnected — reconnecting...", "WARN")
                mt5.shutdown()
                time.sleep(5)
                mt5.initialize()
                mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)
                log("MT5 reconnected")
        except: pass
