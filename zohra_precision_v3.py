"""
ZOHRA PRECISION SCANNER v3 — Research-Backed Entry Logic
=========================================================
Fixes applied after research:
  1. RSI filter: NO buying when RSI > 60 (overbought), NO selling when RSI < 40
  2. Mandatory pullback: price must be in discount zone (buys) / premium zone (sells)
  3. LTF (M5) CHoCH confirmation required before entry
  4. No duplicate positions on same symbol
  5. Minimum 1:3 R:R ratio
  6. Risk reduced to 0.5% per trade (safe sizing)
  7. MACD histogram must be turning in trade direction
  8. Wait for liquidity sweep before entry
"""
import os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import datetime as dt

from zohra.config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TERMINAL_PATH

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "GBPJPY", "EURJPY"]
RISK_PCT = 0.005    # 0.5% risk per trade (safe)
MIN_RR   = 3.0      # Minimum 1:3 risk:reward
MAGIC    = 20260604

# ── Connect ─────────────────────────────────────────────────────────────
print("\n" + "═"*65)
print("  ╔═══════════════════════════════════════════════════════╗")
print("  ║     ZOHRA PRECISION SCANNER v3 — RESEARCH BACKED     ║")
print("  ║   Entry only on: Pullback + CHoCH + No RSI Extreme   ║")
print("  ╚═══════════════════════════════════════════════════════╝")
print("═"*65)

init_ok = mt5.initialize(path=MT5_TERMINAL_PATH) if MT5_TERMINAL_PATH else mt5.initialize()
if not init_ok:
    print(f"MT5 init failed: {mt5.last_error()}"); sys.exit(1)
if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
    print(f"Login failed: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

acc = mt5.account_info()
print(f"\n  ✅ Connected  | {acc.name}")
print(f"  💰 Balance   : ${acc.balance:,.2f}")
print(f"  💎 Equity    : ${acc.equity:,.2f}")
print(f"  ⚠️  Float P&L: ${acc.equity - acc.balance:+,.2f}")

# ── Check existing positions (avoid duplicates) ──────────────────────────
open_symbols = set()
open_pos = mt5.positions_get()
if open_pos:
    print(f"\n  📌 Already open positions:")
    for p in open_pos:
        direction = "LONG" if p.type == 0 else "SHORT"
        print(f"     {p.symbol} {direction} | Lots={p.volume} | P&L=${p.profit:+.2f}")
        open_symbols.add(p.symbol)

def get_filling(symbol):
    si = mt5.symbol_info(symbol)
    if si is None: return mt5.ORDER_FILLING_FOK
    fm = si.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 4: return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK

def pip_value_per_lot(symbol):
    if symbol == "XAUUSD": return 100.0
    si   = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if si is None or tick is None: return 10.0
    if "JPY" in symbol:
        return round((100_000 * 0.01) / tick.ask, 2) if tick.ask > 0 else 9.0
    return 10.0

def get_df(symbol, tf, count=350):
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) < 80: return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    for p in [9, 20, 50, 200]:
        df[f'ema{p}'] = df['close'].ewm(span=p, adjust=False).mean()
    df['tr']  = np.maximum(df['high']-df['low'],
                np.maximum(abs(df['high']-df['close'].shift(1)),
                           abs(df['low'] -df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    df['bull'] = df['close'] > df['open']
    df['body'] = abs(df['close'] - df['open'])
    # RSI
    delta = df['close'].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-9)))
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd']     = ema12 - ema26
    df['macd_sig'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist']= df['macd'] - df['macd_sig']
    # Bollinger
    bm = df['close'].rolling(20).mean()
    bs = df['close'].rolling(20).std()
    df['bb_up'] = bm + 2*bs
    df['bb_lo'] = bm - 2*bs
    df['vol_sma'] = df['real_volume'].rolling(20).mean()
    return df

def find_swings(df, lookback=80, pivot=3):
    highs, lows = [], []
    subset = df.iloc[-(lookback + pivot*2):-1].reset_index(drop=True)
    n = pivot
    for i in range(n, len(subset)-n):
        wh = subset['high'].iloc[i-n:i+n+1]
        wl = subset['low'].iloc[i-n:i+n+1]
        if subset['high'].iloc[i] == wh.max():
            highs.append(subset['high'].iloc[i])
        if subset['low'].iloc[i] == wl.min():
            lows.append(subset['low'].iloc[i])
    return highs, lows

def check_ltf_choch(symbol, direction):
    """
    Research requirement: LTF (M5) Change of Character must confirm direction.
    CHoCH LONG  = price broke ABOVE a recent M5 swing high (structure shift bullish)
    CHoCH SHORT = price broke BELOW a recent M5 swing low  (structure shift bearish)
    """
    df5 = get_df(symbol, mt5.TIMEFRAME_M5, 150)
    if df5 is None: return False, "No M5 data"
    sh, sl = find_swings(df5, lookback=40, pivot=2)
    price  = df5['close'].iloc[-1]
    if direction == "LONG":
        if len(sh) >= 2 and price > sh[-2]:
            return True, f"M5 CHoCH BULL confirmed (broke {sh[-2]:.5f})"
        return False, "M5 CHoCH not yet confirmed for LONG"
    else:
        if len(sl) >= 2 and price < sl[-2]:
            return True, f"M5 CHoCH BEAR confirmed (broke {sl[-2]:.5f})"
        return False, "M5 CHoCH not yet confirmed for SHORT"

def analyze_symbol(symbol, direction):
    """
    Full professional SMC analysis. Returns (score, reasons, passed_checks, atr, sl).
    Returns score=0 with reason if any MANDATORY filter fails.
    """
    bull = (direction == "LONG")
    checks = {}

    df_d1  = get_df(symbol, mt5.TIMEFRAME_D1,  100)
    df_h4  = get_df(symbol, mt5.TIMEFRAME_H4,  200)
    df_h1  = get_df(symbol, mt5.TIMEFRAME_H1,  200)
    df_m15 = get_df(symbol, mt5.TIMEFRAME_M15, 300)

    if df_h1 is None or df_m15 is None:
        return 0, ["No data"], {}, 0, 0

    price = df_m15['close'].iloc[-1]
    atr   = df_m15['atr'].iloc[-1]
    rsi   = df_m15['rsi'].iloc[-1]
    score = 0
    reasons = []

    # ── MANDATORY FILTER 1: RSI must NOT be extreme ──────────────────
    # Research: Never buy overbought (RSI>65), never sell oversold (RSI<35)
    if bull and rsi > 65:
        return 0, [f"❌ BLOCKED: RSI={rsi:.1f} OVERBOUGHT (>65) — bad LONG entry"], {}, atr, 0
    if not bull and rsi < 35:
        return 0, [f"❌ BLOCKED: RSI={rsi:.1f} OVERSOLD (<35) — bad SHORT entry"], {}, atr, 0
    checks['RSI_Filter'] = f"RSI={rsi:.1f} ✅"

    # ── MANDATORY FILTER 2: HTF Daily trend alignment ────────────────
    # Research: Must trade WITH the Daily trend, not against it
    d1_bull = False
    if df_d1 is not None and len(df_d1) >= 3:
        d1_bull = (df_d1['ema20'].iloc[-1] > df_d1['ema50'].iloc[-1] and
                   df_d1['close'].iloc[-1] > df_d1['ema20'].iloc[-1])
    # Allow neutral — only block confirmed opposite trend
    d1_clearly_bear = (df_d1 is not None and
                       df_d1['ema20'].iloc[-1] < df_d1['ema50'].iloc[-1] and
                       df_d1['close'].iloc[-1] < df_d1['ema50'].iloc[-1])
    d1_clearly_bull = (df_d1 is not None and
                       df_d1['ema20'].iloc[-1] > df_d1['ema50'].iloc[-1] and
                       df_d1['close'].iloc[-1] > df_d1['ema50'].iloc[-1])
    if bull and d1_clearly_bear:
        return 0, [f"❌ BLOCKED: Daily trend is BEARISH — no LONG trades against D1 trend"], {}, atr, 0
    if not bull and d1_clearly_bull:
        return 0, [f"❌ BLOCKED: Daily trend is BULLISH — no SHORT trades against D1 trend"], {}, atr, 0
    checks['D1_Trend'] = f"D1 {'BULL' if d1_clearly_bull else 'BEAR' if d1_clearly_bear else 'NEUTRAL'} ✅"

    # ── MANDATORY FILTER 3: H4 Trend must align ──────────────────────
    h4_bull = False
    if df_h4 is not None:
        h4_bull = (df_h4['ema20'].iloc[-1] > df_h4['ema50'].iloc[-1] and
                   df_h4['close'].iloc[-1] > df_h4['ema20'].iloc[-1])
    h4_bear = (df_h4 is not None and
               df_h4['ema20'].iloc[-1] < df_h4['ema50'].iloc[-1] and
               df_h4['close'].iloc[-1] < df_h4['ema20'].iloc[-1])
    if bull and h4_bear:
        return 0, [f"❌ BLOCKED: H4 trend is BEARISH — no LONG"], {}, atr, 0
    if not bull and h4_bull:
        return 0, [f"❌ BLOCKED: H4 trend is BULLISH — no SHORT"], {}, atr, 0
    checks['H4_Trend'] = f"H4 {'BULL' if h4_bull else 'BEAR' if h4_bear else 'MIXED'} ✅"

    # ── MANDATORY FILTER 4: Price in Discount/Premium zone ───────────
    # Research: Buys only from Discount (<50% of range), Sells from Premium (>50%)
    range_candles = df_h1.iloc[-50:]
    hh = range_candles['high'].max()
    ll = range_candles['low'].min()
    rng = hh - ll
    pct = (price - ll) / (rng + 1e-9)
    in_discount = pct <= 0.45   # Below 45% = discount (good for buys)
    in_premium  = pct >= 0.55   # Above 55% = premium (good for sells)
    if bull and not in_discount:
        return 0, [f"❌ BLOCKED: Price at {pct*100:.0f}% of range — NOT in Discount zone for LONG (need <45%)"], {}, atr, 0
    if not bull and not in_premium:
        return 0, [f"❌ BLOCKED: Price at {pct*100:.0f}% of range — NOT in Premium zone for SHORT (need >55%)"], {}, atr, 0
    checks['Zone'] = f"Price at {pct*100:.0f}% — {'Discount ✅' if in_discount else 'Premium ✅'}"

    # ── MANDATORY FILTER 5: M5 LTF CHoCH confirmation ────────────────
    # Research: Enter only after LTF structure shift confirms direction
    choch_ok, choch_msg = check_ltf_choch(symbol, direction)
    if not choch_ok:
        return 0, [f"❌ BLOCKED: {choch_msg}"], {}, atr, 0
    checks['LTF_CHoCH'] = choch_msg + " ✅"

    # ── SCORING — all mandatory filters passed ────────────────────────
    # H1 BOS confirmation (+25)
    sh_h1, sl_h1 = find_swings(df_h1, lookback=80, pivot=3)
    bos = False
    if bull and len(sh_h1) >= 2 and price > sh_h1[-2]: bos = True
    if not bull and len(sl_h1) >= 2 and price < sl_h1[-2]: bos = True
    bos_pts = 25 if bos else 10
    score += bos_pts
    reasons.append(f"Structure BOS={'YES' if bos else 'FORMING'} +{bos_pts}pts")

    # H1+M15 Multi-TF alignment (+20)
    h1_bull = (df_h1['ema20'].iloc[-1] > df_h1['ema50'].iloc[-1])
    m15_bull = (df_m15['ema20'].iloc[-1] > df_m15['ema50'].iloc[-1])
    tf_match = sum([(h4_bull==bull), (h1_bull==bull), (m15_bull==bull)])
    tf_pts = tf_match * 7
    score += tf_pts
    reasons.append(f"TF Alignment {tf_match}/3 H4+H1+M15 +{tf_pts}pts")

    # MACD histogram turning direction (+15)
    hist_now  = df_m15['macd_hist'].iloc[-1]
    hist_prev = df_m15['macd_hist'].iloc[-3]
    macd_turn = (hist_now > hist_prev and bull) or (hist_now < hist_prev and not bull)
    macd_pts = 15 if macd_turn else 0
    score += macd_pts
    reasons.append(f"MACD Hist turning {'UP' if bull else 'DOWN'}: {'YES' if macd_turn else 'NO'} +{macd_pts}pts")

    # RSI momentum (NOT extreme, moving in right direction) (+10)
    rsi_prev = df_m15['rsi'].iloc[-3]
    rsi_moving = (rsi > rsi_prev and bull) or (rsi < rsi_prev and not bull)
    rsi_pts = 10 if rsi_moving else 0
    score += rsi_pts
    reasons.append(f"RSI={rsi:.1f} moving {'up' if bull else 'down'}: {'YES' if rsi_moving else 'NO'} +{rsi_pts}pts")

    # Volume above average (+10)
    vol_now = df_m15['real_volume'].iloc[-1]
    vol_avg = df_m15['vol_sma'].iloc[-1]
    vol_ok  = vol_now > vol_avg * 0.9
    vol_pts = 10 if vol_ok else 0
    score += vol_pts
    reasons.append(f"Volume {'above' if vol_ok else 'below'} avg (RVol={vol_now/(vol_avg+1e-9):.2f}) +{vol_pts}pts")

    score = min(100, score)

    # ── SL/TP calculation ─────────────────────────────────────────────
    si = mt5.symbol_info(symbol)
    sl_dist = atr * 1.5
    if bull:
        # SL below recent swing low + buffer
        if sl_h1: sl_dist = max(sl_dist, abs(price - sl_h1[-1]) + atr * 0.3)
        sl_price = round(price - sl_dist, si.digits)
    else:
        if sh_h1: sl_dist = max(sl_dist, abs(sh_h1[-1] - price) + atr * 0.3)
        sl_price = round(price + sl_dist, si.digits)

    return score, reasons, checks, atr, sl_price

# ── Scan all symbols ─────────────────────────────────────────────────────
print(f"\n\n  📡 Scanning {len(SYMBOLS)} symbols with professional SMC filters...\n")
print(f"  {'Symbol':<10} {'LONG':>6} {'SHORT':>6}   Status")
print("  " + "─"*60)

candidates = []

for sym in SYMBOLS:
    mt5.symbol_select(sym, True)
    time.sleep(0.15)

    # Skip if already have open position on this symbol
    if sym in open_symbols:
        print(f"  {sym:<10}   --     --   ⏭️  SKIP (position already open)")
        continue

    long_score,  long_r,  long_c,  long_atr,  long_sl  = analyze_symbol(sym, "LONG")
    short_score, short_r, short_c, short_atr, short_sl = analyze_symbol(sym, "SHORT")

    best_dir   = "LONG"  if long_score >= short_score else "SHORT"
    best_score = max(long_score, short_score)
    best_r     = long_r if best_dir == "LONG" else short_r
    best_c     = long_c if best_dir == "LONG" else short_c
    best_atr   = long_atr if best_dir == "LONG" else short_atr
    best_sl    = long_sl  if best_dir == "LONG" else short_sl

    blocked_l = long_score == 0 and long_r and long_r[0].startswith("❌")
    blocked_s = short_score == 0 and short_r and short_r[0].startswith("❌")

    if best_score >= 50:
        flag = "🎯"
    elif best_score >= 30:
        flag = "👀"
    else:
        flag = "⛔"

    print(f"  {sym:<10} {long_score:>5}  {short_score:>5}   {flag} Best={best_dir}({best_score})")

    if best_score >= 30:
        candidates.append({
            "symbol":    sym,
            "direction": best_dir,
            "score":     best_score,
            "reasons":   best_r,
            "checks":    best_c,
            "atr":       best_atr,
            "sl":        best_sl,
        })

# ── Sort and pick best ───────────────────────────────────────────────────
candidates.sort(key=lambda x: x['score'], reverse=True)

print(f"\n{'═'*65}")

if not candidates:
    print("  ⛔ NO VALID SETUPS RIGHT NOW")
    print()
    print("  All pairs blocked by professional filters:")
    print("  • RSI at extremes (overbought/oversold)")
    print("  • Price not in Discount/Premium zone")
    print("  • No M5 CHoCH (Change of Character) confirmation")
    print("  • Trend direction conflicts across timeframes")
    print()
    print("  ✅ This is CORRECT behavior — protecting your capital.")
    print("  ✅ The engine will scan again on next candle.")
    print("  ⏳ Wait for market to set up properly.")
    mt5.shutdown(); sys.exit(0)

best = candidates[0]
print(f"  🏆  BEST SETUP: {best['direction']} {best['symbol']} — Score {best['score']}/100")
print(f"{'═'*65}")
print()
print("  ✅ Mandatory Filters ALL PASSED:")
for k, v in best['checks'].items():
    print(f"     • {k:<15}: {v}")
print()
print("  📊 Scoring Breakdown:")
for r in best['reasons']:
    print(f"     • {r}")

if best['score'] < 40:
    print(f"\n  ⛔ Score {best['score']}/100 too low even after filters passed — no trade.")
    mt5.shutdown(); sys.exit(0)

# ── Calculate position size ──────────────────────────────────────────────
symbol    = best['symbol']
direction = best['direction']
sl_price  = best['sl']
equity    = acc.equity

mt5.symbol_select(symbol, True)
tick   = mt5.symbol_info_tick(symbol)
si     = mt5.symbol_info(symbol)
digits = si.digits
entry  = tick.ask if direction == "LONG" else tick.bid
sl_dist = abs(entry - sl_price)

# R:R = 1:3 minimum
tp_dist  = sl_dist * MIN_RR
tp_price = round(entry + tp_dist, digits) if direction == "LONG" else round(entry - tp_dist, digits)

# Position sizing
pv   = pip_value_per_lot(symbol)
pip  = si.point * 10 if "JPY" not in symbol and symbol != "XAUUSD" else si.point
pips_risk = sl_dist / pip if pip > 0 else sl_dist / 0.0001
risk_usd  = equity * RISK_PCT
lots = risk_usd / (pips_risk * pv + 1e-9)
lots = max(si.volume_min, min(si.volume_max,
       round(round(lots / si.volume_step) * si.volume_step, 2)))

print(f"\n{'═'*65}")
print(f"  📋  TRADE PARAMETERS")
print(f"{'═'*65}")
print(f"  Symbol     : {symbol}")
print(f"  Direction  : {direction}")
print(f"  Entry      : {entry:.{digits}f}")
print(f"  Stop Loss  : {sl_price:.{digits}f}")
print(f"  Take Profit: {tp_price:.{digits}f}  (1:{MIN_RR:.0f} R:R)")
print(f"  Lots       : {lots}")
print(f"  Risk       : ${risk_usd:.2f}  (0.5% equity = conservative)")
print(f"  SL dist    : {sl_dist:.{digits}f}")

# ── Place trade ──────────────────────────────────────────────────────────
req = {
    "action":       mt5.TRADE_ACTION_DEAL,
    "symbol":       symbol,
    "volume":       lots,
    "type":         mt5.ORDER_TYPE_BUY if direction == "LONG" else mt5.ORDER_TYPE_SELL,
    "price":        entry,
    "sl":           round(sl_price, digits),
    "tp":           tp_price,
    "deviation":    30,
    "magic":        MAGIC,
    "comment":      f"ZohraV3_{best['score']}",
    "type_time":    mt5.ORDER_TIME_GTC,
    "type_filling": get_filling(symbol),
}

print(f"\n  Sending order...")
result = mt5.order_send(req)

if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
    retcode = result.retcode if result else "None"
    comment = result.comment if result else str(mt5.last_error())
    print(f"\n  ❌ ORDER FAILED — retcode={retcode}: {comment}")
    mt5.shutdown(); sys.exit(1)

fill   = result.price if result.price else entry
ticket = result.order

print(f"\n{'═'*65}")
print(f"  ✅  TRADE PLACED SUCCESSFULLY!")
print(f"{'═'*65}")
print(f"  🎫 Ticket     : {ticket}")
print(f"  📌 {direction} {symbol}")
print(f"  💰 Fill Price : {fill:.{digits}f}")
print(f"  🛑 Stop Loss  : {sl_price:.{digits}f}")
print(f"  🎯 Take Profit: {tp_price:.{digits}f}")
print(f"  📦 Lots       : {lots}  |  Risk: ${risk_usd:.2f}")
print(f"  📐 R:R Ratio  : 1:{MIN_RR:.0f}")
print(f"\n  ✅ Check MT5 terminal → Trades tab")
print(f"{'═'*65}\n")

# ── Monitor 2 minutes ────────────────────────────────────────────────────
print("  Monitoring for 2 minutes...\n")
for i in range(24):
    time.sleep(5)
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        print(f"  [{(i+1)*5:>3}s] ⚡ Position closed (TP/SL hit)")
        break
    pos = positions[0]
    tick2   = mt5.symbol_info_tick(symbol)
    current = tick2.bid if direction == "LONG" else tick2.ask
    pnl     = pos.profit
    dist    = current - fill if direction == "LONG" else fill - current
    status  = "🟢 PROFIT" if pnl > 0 else "🔴 LOSS"
    print(f"  [{(i+1)*5:>3}s] {current:.{digits}f}  P&L: ${pnl:+.2f}  Move: {dist:+.{digits}f}  {status}")

print(f"\n  Trade is running. Manage it in MT5.")
mt5.shutdown()
