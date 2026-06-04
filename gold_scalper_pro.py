"""
╔══════════════════════════════════════════════════════════════════╗
║          XAUUSD PROFESSIONAL SCALPING ENGINE                    ║
║          Capital Preservation First. Profits Second.            ║
╚══════════════════════════════════════════════════════════════════╝

ARCHITECTURE:
  1. Session Filter       → only trade high-liquidity windows
  2. Market Structure     → trend vs range detection on H1/M15
  3. Confidence Scorer    → multi-confirmation score (0-100)
  4. Smart SL Placement   → behind swing high/low on M5
  5. Risk Engine          → fixed % risk, daily halt, drawdown guard
  6. Position Manager     → partial close at 1R, trail the rest
  7. Trade Journal        → CSV log: entry reason, exit, R/R, conditions
"""

import os, sys, time, csv, math
import datetime as dt
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# ══════════════════════════════════════════════════════════════════════
#  ⚙  CONFIGURATION  — tune these to change behaviour
# ══════════════════════════════════════════════════════════════════════
SYMBOL            = "XAUUSD"
MAGIC             = 20240601

# Risk Engine
RISK_PCT_PER_TRADE = 0.005      # 0.5 % of equity per trade
DAILY_LOSS_LIMIT   = -50.0      # Halt ALL trading if day P&L <= -$50
MAX_DRAWDOWN_USD   = -80.0      # Halt if equity drops $80 from session start
MIN_LOT            = 0.01
MAX_LOT            = 1.00       # Allow up to 1 lot for a $100k account
# SL is ATR-based (see smart_sl). These are fallback clamps:
SL_MIN_PTS         = 100        # Never less than 100 pts ($1.00 move)
SL_MAX_MULT        = 2.5        # Never more than 2.5x M5 ATR

# Entry Confidence
MIN_CONFIDENCE     = 70         # Raised from 60 — only high-quality setups
HARD_SESSION_BLOCK = True       # Hard-refuse trades outside active sessions
MAX_CONCURRENT     = 3          # Max open scalp positions at once

# Position Management
PARTIAL_CLOSE_AT_R = 1.0        # Close 50 % of position at 1R profit
TRAIL_STEP_PTS     = 80         # Trail SL by 80 pts after partial close
FULL_CLOSE_AT_R    = 2.0        # Close remaining 50 % at 2R
FORCE_CUT_USD      = -15.0      # Emergency cut per individual trade

# Session Windows (UTC hours)  Best Gold liquidity:
SESSIONS = {
    "London":  (7,  16),    # 07:00–16:00 UTC
    "NewYork": (12, 21),    # 12:00–21:00 UTC
    "Overlap": (13, 17),    # 13:00–17:00 UTC  ← highest priority
}
TRADE_IN_SESSIONS  = ["Overlap", "London", "NewYork"]

# Journal
JOURNAL_FILE       = os.path.join(os.path.dirname(__file__),
                                   "logs", "trade_journal.csv")

# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════
def now_utc():
    return dt.datetime.now(dt.timezone.utc)

def ts():
    return now_utc().strftime("%H:%M:%S")

def banner(text, char="═"):
    line = char * 65
    print(f"\n{line}\n  {text}\n{line}")

def section(text):
    print(f"\n  {'─'*60}\n  {text}\n  {'─'*60}")

def get_filling():
    info = mt5.symbol_info(SYMBOL)
    if info is None: return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 4: return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK

def get_df(tf, count=200):
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    if rates is None or len(rates) < 50:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    # EMAs
    for span in [9, 20, 21, 50]:
        df[f'ema{span}'] = df['close'].ewm(span=span, adjust=False).mean()
    # RSI
    d     = df['close'].diff()
    gain  = d.clip(lower=0).rolling(14).mean()
    loss  = (-d.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    # ATR
    df['tr'] = np.maximum(df['high'] - df['low'],
               np.maximum(abs(df['high'] - df['close'].shift(1)),
                          abs(df['low']  - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    # Bollinger Bands (20,2)
    df['bb_mid']  = df['close'].rolling(20).mean()
    df['bb_std']  = df['close'].rolling(20).std()
    df['bb_upper']= df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower']= df['bb_mid'] - 2 * df['bb_std']
    # Candle direction
    df['bull_candle'] = df['close'] > df['open']
    return df

def find_swing_levels(df, lookback=30):
    """Find swing highs and lows in last N candles."""
    highs, lows = [], []
    subset = df.iloc[-lookback-2:-1]  # exclude live candle
    for i in range(1, len(subset) - 1):
        if subset['high'].iloc[i] > subset['high'].iloc[i-1] and \
           subset['high'].iloc[i] > subset['high'].iloc[i+1]:
            highs.append(subset['high'].iloc[i])
        if subset['low'].iloc[i] < subset['low'].iloc[i-1] and \
           subset['low'].iloc[i] < subset['low'].iloc[i+1]:
            lows.append(subset['low'].iloc[i])
    return sorted(highs, reverse=True)[:3], sorted(lows)[:3]

# ══════════════════════════════════════════════════════════════════════
#  MODULE 1 — SESSION FILTER
# ══════════════════════════════════════════════════════════════════════
def check_session():
    hour = now_utc().hour
    active = []
    for name, (start, end) in SESSIONS.items():
        if start <= hour < end:
            active.append(name)
    tradeable = [s for s in active if s in TRADE_IN_SESSIONS]
    return active, tradeable

# ══════════════════════════════════════════════════════════════════════
#  MODULE 2 — MARKET STRUCTURE ANALYSER
# ══════════════════════════════════════════════════════════════════════
def analyse_market():
    """
    Returns dict with structure analysis across H1, M15, M5.
    """
    df_h1  = get_df(mt5.TIMEFRAME_H1,  100)
    df_m15 = get_df(mt5.TIMEFRAME_M15, 100)
    df_m5  = get_df(mt5.TIMEFRAME_M5,  100)
    df_m1  = get_df(mt5.TIMEFRAME_M1,   60)

    if any(d is None for d in [df_h1, df_m15, df_m5, df_m1]):
        return None

    h1  = df_h1.iloc[-1]
    m15 = df_m15.iloc[-1]
    m5  = df_m5.iloc[-1]
    m1  = df_m1.iloc[-1]

    # Trend on each TF
    h1_bull  = h1['ema20']  > h1['ema50']
    m15_bull = m15['ema20'] > m15['ema50']
    m5_bull  = m5['ema9']   > m5['ema21']
    m1_bull  = m1['ema9']   > m1['ema21']

    # Momentum
    rsi_m5   = m5['rsi']
    rsi_m1   = m1['rsi']
    atr_m5   = m5['atr']
    atr_m1   = m1['atr']

    # ATR relative to average (is volatility healthy?)
    atr_avg_m5 = df_m5['atr'].iloc[-20:].mean()
    atr_ratio  = atr_m5 / atr_avg_m5 if atr_avg_m5 > 0 else 1.0

    # Market structure: trending vs ranging
    h1_range  = df_h1['high'].iloc[-20:].max() - df_h1['low'].iloc[-20:].min()
    h1_ema_spread = abs(h1['ema20'] - h1['ema50'])
    trending  = (h1_ema_spread / h1_range) > 0.15 if h1_range > 0 else False

    # Swing S/R on M5
    swing_highs, swing_lows = find_swing_levels(df_m5, lookback=40)
    price = m1['close']

    # Nearest S/R
    nearest_r = min(swing_highs, key=lambda x: abs(x - price)) if swing_highs else price + 5
    nearest_s = min(swing_lows,  key=lambda x: abs(x - price)) if swing_lows  else price - 5

    # Consecutive M1 candles in direction
    last5_m1 = df_m1.iloc[-6:-1]
    bull_streak = 0
    bear_streak = 0
    for _, row in last5_m1.iloc[::-1].iterrows():
        if row['close'] > row['open']:
            if bear_streak > 0: break
            bull_streak += 1
        else:
            if bull_streak > 0: break
            bear_streak += 1

    return {
        "price":        price,
        "h1_bull":      h1_bull,
        "m15_bull":     m15_bull,
        "m5_bull":      m5_bull,
        "m1_bull":      m1_bull,
        "rsi_m5":       rsi_m5,
        "rsi_m1":       rsi_m1,
        "atr_m5":       atr_m5,
        "atr_m1":       atr_m1,
        "atr_ratio":    atr_ratio,
        "trending":     trending,
        "swing_highs":  swing_highs,
        "swing_lows":   swing_lows,
        "nearest_r":    nearest_r,
        "nearest_s":    nearest_s,
        "bull_streak":  bull_streak,
        "bear_streak":  bear_streak,
        "bb_upper":     m5['bb_upper'],
        "bb_lower":     m5['bb_lower'],
        "bb_mid":       m5['bb_mid'],
        "df_m5":        df_m5,
    }

# ══════════════════════════════════════════════════════════════════════
#  MODULE 3 — CONFIDENCE SCORER  (0-100)
# ══════════════════════════════════════════════════════════════════════
def score_setup(m, session_ok, direction):
    """
    Score a potential trade setup. Returns (score, reasons_list).
    """
    score   = 0
    reasons = []
    skips   = []

    bull = (direction == "LONG")

    # ── 1. H1 Trend alignment (25 pts) ────────────────────────────────
    if m['h1_bull'] == bull:
        score += 25
        reasons.append(f"  [+25] H1 trend aligned ({direction})")
    else:
        skips.append(  f"  [ 0] H1 trend AGAINST {direction} (major risk)")

    # ── 2. M15 Trend alignment (15 pts) ───────────────────────────────
    if m['m15_bull'] == bull:
        score += 15
        reasons.append(f"  [+15] M15 trend aligned")
    else:
        skips.append(  f"  [ 0] M15 trend against")

    # ── 3. M5 EMA aligned (10 pts) ────────────────────────────────────
    if m['m5_bull'] == bull:
        score += 10
        reasons.append(f"  [+10] M5 EMA9 > EMA21 aligned")
    else:
        skips.append(  f"  [ 0] M5 EMA against")

    # ── 4. RSI momentum (10 pts) ──────────────────────────────────────
    rsi = m['rsi_m5']
    if bull and 45 < rsi < 72:
        score += 10
        reasons.append(f"  [+10] RSI {rsi:.0f} — bullish momentum zone")
    elif not bull and 28 < rsi < 55:
        score += 10
        reasons.append(f"  [+10] RSI {rsi:.0f} — bearish momentum zone")
    elif bull and rsi >= 72:
        skips.append(  f"  [ 0] RSI {rsi:.0f} overbought — risky long")
    elif not bull and rsi <= 28:
        skips.append(  f"  [ 0] RSI {rsi:.0f} oversold — risky short")
    else:
        skips.append(  f"  [ 0] RSI {rsi:.0f} — neutral")

    # ── 5. Price near S/R (10 pts) ────────────────────────────────────
    price    = m['price']
    dist_r   = abs(price - m['nearest_r'])
    dist_s   = abs(price - m['nearest_s'])
    atr      = m['atr_m5']

    if bull and dist_s < atr * 0.5:
        score += 10
        reasons.append(f"  [+10] Price near support ${m['nearest_s']:.2f} (+{dist_s:.2f})")
    elif not bull and dist_r < atr * 0.5:
        score += 10
        reasons.append(f"  [+10] Price near resistance ${m['nearest_r']:.2f} ({dist_r:.2f})")
    else:
        skips.append(  f"  [ 0] Not at key S/R level")

    # ── 6. Volatility (ATR in healthy range) (10 pts) ─────────────────
    if 0.7 < m['atr_ratio'] < 1.8:
        score += 10
        reasons.append(f"  [+10] ATR ratio {m['atr_ratio']:.2f} — healthy volatility")
    elif m['atr_ratio'] >= 1.8:
        skips.append(  f"  [ 0] ATR ratio {m['atr_ratio']:.2f} — too volatile")
    else:
        skips.append(  f"  [ 0] ATR ratio {m['atr_ratio']:.2f} — too quiet")

    # ── 7. Session timing (10 pts) ────────────────────────────────────
    if session_ok:
        score += 10
        reasons.append(f"  [+10] Active trading session")
    else:
        skips.append(  f"  [ 0] Off-peak session")

    # ── 8. M1 candle momentum (10 pts) ────────────────────────────────
    streak = m['bull_streak'] if bull else m['bear_streak']
    if streak >= 2:
        score += 10
        reasons.append(f"  [+10] {streak} consecutive M1 {'bull' if bull else 'bear'} candles")
    elif streak == 1:
        score += 5
        reasons.append(f"  [ +5] 1 M1 confirmation candle")
    else:
        skips.append(  f"  [ 0] No M1 candle confirmation")

    return score, reasons, skips

# ══════════════════════════════════════════════════════════════════════
#  MODULE 4 — RISK ENGINE
# ══════════════════════════════════════════════════════════════════════
def calc_lot_size(equity, sl_points):
    """
    Risk fixed % of equity. SL in points.
    XAUUSD: 1 lot = 100 oz. 1 point ($0.01 move) = $1 P&L per lot.
    So: dollars_per_point_per_lot = 1.0  (NOT 100 — that was the bug)
    """
    si          = mt5.symbol_info(SYMBOL)
    risk_usd    = equity * RISK_PCT_PER_TRADE
    # Correct formula: lots = risk / (sl_pts × $1/pt/lot)
    dollars_per_point_per_lot = 1.0
    lots = risk_usd / (sl_points * dollars_per_point_per_lot)
    lots = max(MIN_LOT, min(MAX_LOT, round(round(lots / si.volume_step) * si.volume_step, 2)))
    risk_actual = sl_points * lots * dollars_per_point_per_lot
    return lots, risk_actual

def smart_sl(m, direction, df_m5):
    """
    Place SL behind nearest swing structure on M5.
    Clamp: min=1.0x ATR, max=2.5x ATR  (never arbitrary fixed pts)
    """
    si    = mt5.symbol_info(SYMBOL)
    point = si.point
    atr   = m['atr_m5']
    buf   = 40 * point     # 40-pt buffer beyond swing

    if direction == "LONG":
        sl = m['nearest_s'] - buf if m['swing_lows'] else m['price'] - atr * 1.5
    else:
        sl = m['nearest_r'] + buf if m['swing_highs'] else m['price'] + atr * 1.5

    # Clamp to ATR-based range (fixes the 200-pt bug)
    min_dist = max(SL_MIN_PTS * point, atr * 0.8)   # at least 0.8x ATR
    max_dist = atr * SL_MAX_MULT                      # at most 2.5x ATR

    if direction == "LONG":
        dist = m['price'] - sl
        if dist < min_dist: sl = m['price'] - min_dist
        if dist > max_dist: sl = m['price'] - max_dist
    else:
        dist = sl - m['price']
        if dist < min_dist: sl = m['price'] + min_dist
        if dist > max_dist: sl = m['price'] + max_dist

    return round(sl, si.digits)

# ══════════════════════════════════════════════════════════════════════
#  MODULE 5 — ORDER EXECUTION
# ══════════════════════════════════════════════════════════════════════
def open_trade(direction, sl_price, lots, label=""):
    tick = mt5.symbol_info_tick(SYMBOL)
    si   = mt5.symbol_info(SYMBOL)
    if tick is None: return None, "No tick"

    otype = mt5.ORDER_TYPE_BUY  if direction == "LONG" else mt5.ORDER_TYPE_SELL
    price = tick.ask             if direction == "LONG" else tick.bid

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       lots,
        "type":         otype,
        "price":        price,
        "sl":           round(sl_price, si.digits),
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"ScalpPro_{label}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(),
    }
    r = mt5.order_send(req)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        err = r.comment if r else str(mt5.last_error())
        return None, err
    fill = r.price if r.price else price
    sl_pts = abs(fill - sl_price) / si.point
    tp1    = fill + sl_pts * si.point if direction == "LONG" else fill - sl_pts * si.point
    tp2    = fill + sl_pts * FULL_CLOSE_AT_R * si.point if direction == "LONG" \
             else fill - sl_pts * FULL_CLOSE_AT_R * si.point
    return {
        "ticket":    r.order,
        "entry":     fill,
        "sl":        sl_price,
        "sl_pts":    sl_pts,
        "direction": direction,
        "lots":      lots,
        "lots_orig": lots,
        "tp1":       round(tp1, si.digits),
        "tp2":       round(tp2, si.digits),
        "be_set":    False,
        "partial_done": False,
        "trail_sl":  sl_price,
        "closed":    False,
        "peak_pnl":  0.0,
        "open_time": now_utc().isoformat(),
        "label":     label,
    }, None

def close_trade(t, volume=None, reason=""):
    pos_list = mt5.positions_get(ticket=t['ticket'])
    if not pos_list: return True
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
        "comment":      f"Close_{reason}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(),
    }
    r = mt5.order_send(req)
    return r is not None and r.retcode == mt5.TRADE_RETCODE_DONE

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
#  MODULE 6 — TRADE JOURNAL
# ══════════════════════════════════════════════════════════════════════
def init_journal():
    os.makedirs(os.path.dirname(JOURNAL_FILE), exist_ok=True)
    if not os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, 'w', newline='') as f:
            csv.writer(f).writerow([
                "date","ticket","symbol","direction","lots",
                "entry","sl","tp1","exit_price","pnl_usd",
                "rr_actual","exit_reason","confidence_score",
                "session","h1_trend","market_structure",
                "rsi_at_entry","atr_at_entry","notes"
            ])

def log_trade(t, exit_price, pnl, exit_reason, meta):
    sl_dist = abs(t['entry'] - t['sl'])
    rr = abs(exit_price - t['entry']) / sl_dist if sl_dist > 0 else 0
    if pnl < 0: rr = -rr
    with open(JOURNAL_FILE, 'a', newline='') as f:
        csv.writer(f).writerow([
            now_utc().strftime("%Y-%m-%d"),
            t['ticket'], SYMBOL, t['direction'], t['lots'],
            f"{t['entry']:.2f}", f"{t['sl']:.2f}", f"{t['tp1']:.2f}",
            f"{exit_price:.2f}", f"{pnl:.2f}",
            f"{rr:.2f}", exit_reason,
            meta.get('score', 0), meta.get('session', ''),
            "BULL" if meta.get('h1_bull') else "BEAR",
            "TRENDING" if meta.get('trending') else "RANGING",
            f"{meta.get('rsi', 0):.1f}", f"{meta.get('atr', 0):.2f}",
            meta.get('notes', '')
        ])

# ══════════════════════════════════════════════════════════════════════
#  MODULE 7 — POSITION MANAGER  (active loop)
# ══════════════════════════════════════════════════════════════════════
def manage_trades(trades, day_pnl_ref, session_equity, meta):
    """
    Active management loop. Runs until all trades closed or timeout.
    Returns total realized P&L.
    """
    MAX_SECS   = 420        # 7-minute active management window
    start      = time.time()
    last_print = {}
    realized   = 0.0
    si         = mt5.symbol_info(SYMBOL)
    point      = si.point

    print(f"\n  {'─'*60}")
    print(f"  ACTIVE MANAGER  ({len(trades)} trades)")
    print(f"  Rules: 1R partial close → trail → 2R full close → cut at -${abs(FORCE_CUT_USD)}")
    print(f"  {'─'*60}")
    print(f"\n  {'Time':<10} {'Ticket':<14} {'P&L':>8}  {'Action'}")
    print(f"  {'─'*52}")

    while time.time() - start < MAX_SECS:
        time.sleep(1)

        active = [t for t in trades if not t['closed']]
        if not active:
            print(f"\n  [{ts()}] All positions closed.")
            break

        # Drawdown guard — if session equity dropped too much, close all
        acc = mt5.account_info()
        if acc and (acc.equity - session_equity) <= MAX_DRAWDOWN_USD:
            print(f"\n  [{ts()}] ⛑  MAX DRAWDOWN HIT — closing all positions!")
            for t in active:
                close_trade(t, reason="DRAWDOWN_HALT")
                t['closed'] = True
            break

        for t in active:
            pos_list = mt5.positions_get(ticket=t['ticket'])

            # Position gone (MT5 SL triggered)
            if not pos_list:
                if not t['closed']:
                    t['closed'] = True
                    # Try to get actual exit from recent deals
                    deals = mt5.history_deals_get(
                        dt.datetime.utcnow() - dt.timedelta(minutes=5),
                        dt.datetime.utcnow() + dt.timedelta(seconds=10),
                    )
                    pnl = 0.0
                    exit_p = t['entry']
                    if deals:
                        for d in deals:
                            if d.position_id == t['ticket'] and d.profit != 0:
                                pnl += d.profit
                                exit_p = d.price
                    realized += pnl
                    print(f"  [{ts()}] {t['ticket']:<14} {'---':>8}  ✅ MT5 SL → ${pnl:+.2f}")
                    log_trade(t, exit_p, pnl, "MT5_SL", meta)
                continue

            pos = pos_list[0]
            pnl = pos.profit
            t['peak_pnl'] = max(t.get('peak_pnl', 0.0), pnl)

            # Deduplicate prints
            if last_print.get(t['ticket']) == round(pnl, 1):
                continue
            last_print[t['ticket']] = round(pnl, 1)

            sl_dist_usd = abs(t['entry'] - t['sl']) * t['lots'] * 100
            r_multiple  = pnl / sl_dist_usd if sl_dist_usd > 0 else 0

            # ── RULE A: Emergency cut at -$15 ──────────────────────
            if pnl <= FORCE_CUT_USD:
                ok = close_trade(t, reason="EMERGENCY_CUT")
                t['closed'] = True
                realized   += pnl
                print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  🔴 EMERGENCY CUT -${abs(pnl):.2f}")
                log_trade(t, pos.price_current, pnl, "EMERGENCY_CUT", meta)
                continue

            # ── RULE B: Partial close at 1R (+1× risk amount) ──────
            if not t['partial_done'] and r_multiple >= PARTIAL_CLOSE_AT_R:
                half_lots = round(t['lots'] / 2, 2)
                half_lots = max(si.volume_min, half_lots)
                ok = close_trade(t, volume=half_lots, reason="PARTIAL_1R")
                if ok:
                    t['partial_done'] = True
                    t['lots']        -= half_lots
                    partial_pnl       = pnl / 2
                    realized         += partial_pnl
                    # Move SL to breakeven
                    ok2 = update_sl(t, t['entry'])
                    if ok2:
                        t['be_set']   = True
                        t['trail_sl'] = t['entry']
                    print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  💰 PARTIAL CLOSE 50% @ 1R  BE SET")
                continue

            # ── RULE C: Full close at 2R ───────────────────────────
            if t['partial_done'] and r_multiple >= FULL_CLOSE_AT_R:
                ok = close_trade(t, reason="FULL_2R")
                t['closed'] = True
                realized   += pnl
                print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  🏆 FULL CLOSE @ 2R +${pnl:.2f}")
                log_trade(t, pos.price_current, pnl, "FULL_2R", meta)
                continue

            # ── RULE D: Trail SL after BE set ─────────────────────
            if t['be_set'] and pnl > 0:
                tick_now = mt5.symbol_info_tick(SYMBOL)
                if t['direction'] == "LONG":
                    new_trail = round(tick_now.bid - TRAIL_STEP_PTS * point, si.digits)
                    if new_trail > t['trail_sl'] + point * 10:
                        ok = update_sl(t, new_trail)
                        if ok:
                            t['trail_sl'] = new_trail
                            print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  📈 TRAIL → ${new_trail:.2f}")
                else:
                    new_trail = round(tick_now.ask + TRAIL_STEP_PTS * point, si.digits)
                    if new_trail < t['trail_sl'] - point * 10:
                        ok = update_sl(t, new_trail)
                        if ok:
                            t['trail_sl'] = new_trail
                            print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  📉 TRAIL → ${new_trail:.2f}")

            # ── Status ────────────────────────────────────────────
            flags = ""
            if t['be_set']:       flags += " ⚡BE"
            if t['partial_done']: flags += " 💰50%"
            icon = "🟢" if pnl > 0 else "🔴"
            print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  {icon} Running{flags}  R={r_multiple:+.2f}")

    # Timeout — close all remaining
    remaining = [t for t in trades if not t['closed']]
    if remaining:
        print(f"\n  [{ts()}] ⏱ Timeout — closing {len(remaining)} trade(s)...")
        for t in remaining:
            pos_list = mt5.positions_get(ticket=t['ticket'])
            if pos_list:
                pnl = pos_list[0].profit
                close_trade(t, reason="TIMEOUT")
                t['closed'] = True
                realized += pnl
                log_trade(t, pos_list[0].price_current, pnl, "TIMEOUT", meta)
                print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  ⏱ Closed on timeout")

    return realized

# ══════════════════════════════════════════════════════════════════════
#  MAIN — ENGINE ENTRY POINT
# ══════════════════════════════════════════════════════════════════════
banner("XAUUSD PROFESSIONAL SCALPING ENGINE", "═")
print(f"  Capital Preservation First. Profits Second.")
print(f"  Min confidence: {MIN_CONFIDENCE}/100  |  Risk/trade: {RISK_PCT_PER_TRADE*100:.1f}%")
print(f"  Daily halt: ${DAILY_LOSS_LIMIT}  |  Partial at: {PARTIAL_CLOSE_AT_R}R  |  Full at: {FULL_CLOSE_AT_R}R")

# ── MT5 Connect ───────────────────────────────────────────────────────
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}"); sys.exit(1)
if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
    print(f"Login failed: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

acc = mt5.account_info()
SESSION_EQUITY = acc.equity
print(f"\n  Account : {acc.name}   Balance: ${acc.balance:,.2f}   Equity: ${acc.equity:,.2f}")

if not mt5.symbol_select(SYMBOL, True):
    print(f"  {SYMBOL} not available!"); mt5.shutdown(); sys.exit(1)

init_journal()

# ── SESSION CHECK ─────────────────────────────────────────────────────
section("STEP 1 ▸ Session Analysis")
active_sessions, tradeable_sessions = check_session()
hour_utc = now_utc().hour
session_ok = len(tradeable_sessions) > 0

print(f"\n  UTC Hour       : {hour_utc:02d}:00")
print(f"  Active sessions: {', '.join(active_sessions) if active_sessions else 'NONE (off-hours)'}")
print(f"  Tradeable      : {', '.join(tradeable_sessions) if tradeable_sessions else '⚠️  OFF-PEAK'}")
if HARD_SESSION_BLOCK and not session_ok:
    print(f"\n  ⛔ HARD SESSION BLOCK — market off-peak. No trades.")
    print(f"  Best Gold sessions (UTC): London 07-16 | NY 12-21 | Overlap 13-17")
    print(f"  Current UTC hour: {hour_utc:02d}:00 — come back during London/NY session.")
    mt5.shutdown()
    sys.exit(0)
elif not session_ok:
    print(f"\n  ⚠️  Off-peak session — continuing with score penalty")

# ── MARKET ANALYSIS ───────────────────────────────────────────────────
section("STEP 2 ▸ Market Structure Analysis")
m = analyse_market()
if m is None:
    print("  ERROR: Failed to retrieve market data."); mt5.shutdown(); sys.exit(1)

h1_dir  = "BULL 🟢" if m['h1_bull']  else "BEAR 🔴"
m15_dir = "BULL 🟢" if m['m15_bull'] else "BEAR 🔴"
m5_dir  = "BULL 🟢" if m['m5_bull']  else "BEAR 🔴"
struct  = "TRENDING 📈" if m['trending'] else "RANGING ↔️"

print(f"""
  Gold Price   : ${m['price']:,.2f}
  H1  Trend    : {h1_dir}   (EMA20 vs EMA50)
  M15 Trend    : {m15_dir}  (EMA20 vs EMA50)
  M5  Trend    : {m5_dir}   (EMA9  vs EMA21)
  Structure    : {struct}
  RSI (M5)     : {m['rsi_m5']:.1f}
  ATR (M5)     : ${m['atr_m5']:.2f}  (ratio vs avg: {m['atr_ratio']:.2f}x)
  Swing Highs  : {[f'${x:.2f}' for x in m['swing_highs']]}
  Swing Lows   : {[f'${x:.2f}' for x in m['swing_lows']]}
  Nearest R    : ${m['nearest_r']:.2f}
  Nearest S    : ${m['nearest_s']:.2f}
  M1 Streak    : {m['bull_streak']} bull / {m['bear_streak']} bear candles""")

# Determine candidate direction (majority vote H1+M15+M5)
votes_bull = sum([m['h1_bull'], m['m15_bull'], m['m5_bull']])
DIRECTION  = "LONG" if votes_bull >= 2 else "SHORT"
print(f"\n  Candidate dir  : {DIRECTION}  ({votes_bull}/3 bull votes)")

# ── CONFIDENCE SCORE ──────────────────────────────────────────────────
section("STEP 3 ▸ Confidence Scoring")
score, reasons, skips = score_setup(m, session_ok, DIRECTION)

print(f"\n  ✅ CONFIRMATIONS:")
for r in reasons: print(r)
print(f"\n  ❌ MISSES:")
for s in skips:   print(s)

bar_fill = "█" * (score // 5) + "░" * (20 - score // 5)
verdict  = "✅ TRADE" if score >= MIN_CONFIDENCE else "⛔ SKIP"
print(f"\n  CONFIDENCE SCORE : [{bar_fill}] {score}/100  → {verdict}")

# ── DECISION ──────────────────────────────────────────────────────────
if score < MIN_CONFIDENCE:
    print(f"\n  Score {score} < minimum {MIN_CONFIDENCE} — NO TRADE.")
    print(f"  Reason: Not enough confirmations align. Waiting for better setup.")
    print(f"\n  💡 Come back when:")
    print(f"     • H1, M15, M5 all agree on direction")
    if not session_ok:
        print(f"     • London/NY session is active (13:00–17:00 UTC)")
    mt5.shutdown()
    sys.exit(0)

# ── RISK CALCULATION ──────────────────────────────────────────────────
section("STEP 4 ▸ Risk & Position Sizing")

acc      = mt5.account_info()
equity   = acc.equity
SL_PRICE = smart_sl(m, DIRECTION, m['df_m5'])
sl_dist  = abs(m['price'] - SL_PRICE)
si       = mt5.symbol_info(SYMBOL)
sl_pts   = sl_dist / si.point
lots, risk_usd = calc_lot_size(equity, sl_pts)

tp1_price = round(m['price'] + sl_dist * PARTIAL_CLOSE_AT_R, si.digits) \
            if DIRECTION == "LONG" else \
            round(m['price'] - sl_dist * PARTIAL_CLOSE_AT_R, si.digits)
tp2_price = round(m['price'] + sl_dist * FULL_CLOSE_AT_R, si.digits) \
            if DIRECTION == "LONG" else \
            round(m['price'] - sl_dist * FULL_CLOSE_AT_R, si.digits)

# Correct risk display: sl_pts × lots × $1/pt/lot
risk_actual_usd = sl_pts * lots * 1.0
reward_1r_usd   = risk_actual_usd * PARTIAL_CLOSE_AT_R
reward_2r_usd   = risk_actual_usd * FULL_CLOSE_AT_R

print(f"""
  Direction    : {DIRECTION}
  Entry ~      : ${m['price']:,.2f}
  Stop Loss    : ${SL_PRICE:,.2f}  ({sl_pts:.0f} pts = ${sl_dist:.2f} move)
  TP1 (1R)     : ${tp1_price:,.2f}  → +${reward_1r_usd:.2f} profit on 50%
  TP2 (2R)     : ${tp2_price:,.2f}  → +${reward_2r_usd:.2f} profit on 50%
  Equity       : ${equity:,.2f}
  Risk (0.5%)  : ~${risk_actual_usd:.2f}  (target ${risk_usd:.2f}, capped at {lots} lots)
  Lot size     : {lots} lots
  R/R          : {FULL_CLOSE_AT_R:.1f} : 1""")

# ── OPEN TRADES ───────────────────────────────────────────────────────
section("STEP 5 ▸ Trade Execution")

NUM_TO_OPEN = min(MAX_CONCURRENT, 3)   # open up to 3 confirmed scalps
trades      = []
meta        = {
    "score":     score,
    "session":   ','.join(tradeable_sessions) or "off-peak",
    "h1_bull":   m['h1_bull'],
    "trending":  m['trending'],
    "rsi":       m['rsi_m5'],
    "atr":       m['atr_m5'],
    "notes":     f"Conf={score} Dir={DIRECTION}",
}

print()
for i in range(NUM_TO_OPEN):
    label = f"S{i+1}"

    # Check health before opening 2nd/3rd trade
    if i > 0 and trades:
        time.sleep(15)
        worst = min(
            (mt5.positions_get(ticket=t['ticket']) or [None])[0].profit
            if mt5.positions_get(ticket=t['ticket']) else 0
            for t in trades if not t['closed']
        )
        if worst < -(risk_usd * 0.6):
            print(f"  [{ts()}] {label}: ⛔ SKIP — previous trade at ${worst:.2f}")
            continue
        be_all = all(t['be_set'] for t in trades if not t['closed'])
        if be_all:
            print(f"  [{ts()}] {label}: ⛔ SKIP — existing trades at BE, main move done")
            continue

    t, err = open_trade(DIRECTION, SL_PRICE, lots, label)
    if t is None:
        print(f"  [{ts()}] {label}: ❌ FAILED — {err}")
    else:
        trades.append(t)
        print(f"  [{ts()}] {label}: ✅ Ticket={t['ticket']}  "
              f"Entry=${t['entry']:,.2f}  SL=${SL_PRICE:,.2f}  "
              f"Lots={lots}  Risk=${risk_usd:.2f}")

if not trades:
    print("  No trades placed."); mt5.shutdown(); sys.exit(0)

# ── MANAGE ────────────────────────────────────────────────────────────
day_pnl = 0.0
realized = manage_trades(trades, day_pnl, SESSION_EQUITY, meta)

# ── SESSION SUMMARY ───────────────────────────────────────────────────
banner("SESSION SUMMARY", "═")
acc2   = mt5.account_info()
change = acc2.equity - SESSION_EQUITY

print(f"""
  Trades Placed   : {len(trades)}
  Session P&L     : ${realized:+.2f}
  Equity Change   : ${change:+.2f}
  Opening Equity  : ${SESSION_EQUITY:,.2f}
  Closing Equity  : ${acc2.equity:,.2f}
  Journal         : {JOURNAL_FILE}
""")

# Win/loss from journal
try:
    df_j = pd.read_csv(JOURNAL_FILE)
    if len(df_j) >= 1:
        total  = len(df_j)
        wins   = (df_j['pnl_usd'].astype(float) > 0).sum()
        avg_rr = df_j['rr_actual'].astype(float).mean()
        tot_pnl = df_j['pnl_usd'].astype(float).sum()
        print(f"  ── All-time Journal Stats ──────────────────────────────")
        print(f"  Total trades  : {total}")
        print(f"  Win rate      : {wins/total*100:.1f}%")
        print(f"  Avg R/R       : {avg_rr:.2f}")
        print(f"  Total P&L     : ${tot_pnl:+.2f}")
except Exception:
    pass

print(f"\n{'═'*65}")
mt5.shutdown()
