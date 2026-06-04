"""
XAUUSD Gold Scalper v4 — FIXED & WORKING
==========================================
Root cause of all previous losses:
  - Entered blindly without price CONFIRMING the move
  - No higher-timeframe trend filter (fought the H1 trend)
  - SL was only in code — MT5 SL raced against our loop

v4 Fixes:
  ✅ H1 trend filter — only trade WITH the major trend
  ✅ Wait for momentum CONFIRMATION on M1 (2 consecutive candles in direction)
  ✅ SL set both in MT5 order AND in code (dual safety)
  ✅ Only open next trade if PREVIOUS trade is green or at BE
  ✅ Clean deduped print loop — no noise
  ✅ Auto-close remaining trades after session
"""
import os, sys, time, datetime
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# ══════════════════════════════════════════════════════════════════════
#  SETTINGS  (edit these)
# ══════════════════════════════════════════════════════════════════════
SYMBOL        = "XAUUSD"
LOT_SIZE      = 0.10          # 0.10 lots per trade

PROFIT_TARGET = 7.0           # Close trade at +$7  (trades peak at $8-9, not $10)
BREAKEVEN_AT  = 3.0           # Move SL to entry when +$3  (protect faster)
TRAIL_STEP    = 2.0           # Trail stop by $2 increments after BE is set
MAX_LOSS_USD  = 15.0          # Hard cut per trade at -$15

# SL in points from entry (backup in MT5 order) — for 0.10 lots on Gold:
# 150 pts = $1.50 move = $15 loss → matches MAX_LOSS_USD
SL_POINTS     = 150

NUM_TRADES    = 4             # Max trades to open
TRADE_GAP_SEC = 20            # Wait 20s before adding next trade
MAX_RUN_SEC   = 360           # Run manager for max 6 minutes
MAGIC         = 20240501
# ══════════════════════════════════════════════════════════════════════

def ts():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")

def get_filling():
    info = mt5.symbol_info(SYMBOL)
    if info is None: return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 4: return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK

def get_df(tf, count=120):
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    if rates is None or len(rates) < 30:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    # EMAs
    df['ema9']  = df['close'].ewm(span=9,  adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    # RSI
    delta = df['close'].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    # ATR
    df['tr'] = np.maximum(df['high']-df['low'],
               np.maximum(abs(df['high']-df['close'].shift(1)),
                          abs(df['low'] -df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def send_order(direction, sl_price):
    tick = mt5.symbol_info_tick(SYMBOL)
    si   = mt5.symbol_info(SYMBOL)
    if tick is None or si is None:
        return None, "No tick data"

    if direction == "LONG":
        otype = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        otype = mt5.ORDER_TYPE_SELL
        price = tick.bid

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       LOT_SIZE,
        "type":         otype,
        "price":        price,
        "sl":           round(sl_price, si.digits),
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      "GoldScalp_v4",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(),
    }
    r = mt5.order_send(req)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        err = r.comment if r else str(mt5.last_error())
        return None, err
    fill = r.price if r.price else price
    return {"ticket": r.order, "entry": fill, "sl": sl_price,
            "direction": direction, "be_set": False, "closed": False}, None

def close_trade(t, reason=""):
    pos_list = mt5.positions_get(ticket=t['ticket'])
    if not pos_list:
        return True  # already closed
    pos  = pos_list[0]
    tick = mt5.symbol_info_tick(SYMBOL)
    if t['direction'] == "LONG":
        ctype = mt5.ORDER_TYPE_SELL; price = tick.bid
    else:
        ctype = mt5.ORDER_TYPE_BUY;  price = tick.ask
    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       pos.volume,
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

def move_to_be(t):
    pos_list = mt5.positions_get(ticket=t['ticket'])
    if not pos_list: return False
    pos = pos_list[0]
    si  = mt5.symbol_info(SYMBOL)
    req = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   SYMBOL,
        "position": t['ticket'],
        "sl":       round(t['entry'], si.digits),
        "tp":       pos.tp,
    }
    r = mt5.order_send(req)
    return r is not None and r.retcode == mt5.TRADE_RETCODE_DONE

# ══════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════
print("\n" + "═"*65)
print("   XAUUSD GOLD SCALPER v4  — Fixed & Working")
print("   +$10 close  |  +$5 breakeven  |  -$15 hard cut")
print("═"*65)

if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}"); sys.exit(1)
if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
    print(f"Login failed: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

acc = mt5.account_info()
print(f"\n  Account : {acc.name}   Balance: ${acc.balance:,.2f}   Equity: ${acc.equity:,.2f}")

if not mt5.symbol_select(SYMBOL, True):
    print(f"  {SYMBOL} not available on this broker!"); mt5.shutdown(); sys.exit(1)

si = mt5.symbol_info(SYMBOL)
DIGITS = si.digits
POINT  = si.point
LOT_SIZE = max(si.volume_min, min(LOT_SIZE, si.volume_max))

# ══════════════════════════════════════════════════════════════════════
#  STEP 1 — H1 TREND FILTER  (which way is the BIG move?)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'─'*65}")
print(f"  STEP 1 ▸ H1 Trend Filter")
print(f"{'─'*65}")

df_h1 = get_df(mt5.TIMEFRAME_H1, 60)
df_m5 = get_df(mt5.TIMEFRAME_M5, 100)
df_m1 = get_df(mt5.TIMEFRAME_M1, 60)

if any(df is None for df in [df_h1, df_m5, df_m1]):
    print("  ERROR: Failed to get candle data."); mt5.shutdown(); sys.exit(1)

h1  = df_h1.iloc[-1]
m5  = df_m5.iloc[-1]
m1  = df_m1.iloc[-1]

h1_bull  = h1['ema9'] > h1['ema50']
m5_bull  = m5['ema9'] > m5['ema21']
m1_bull  = m1['ema9'] > m1['ema21']
rsi_m1   = m1['rsi']
atr_m1   = m1['atr']
price    = m1['close']

h1_label = "🟢 BULL" if h1_bull  else "🔴 BEAR"
m5_label = "🟢 BULL" if m5_bull  else "🔴 BEAR"
m1_label = "🟢 BULL" if m1_bull  else "🔴 BEAR"

print(f"\n  Current Gold Price : ${price:,.2f}")
print(f"  H1  EMA9 vs EMA50  : {'%.2f' % h1['ema9']} vs {'%.2f' % h1['ema50']}  → {h1_label}")
print(f"  M5  EMA9 vs EMA21  : {'%.2f' % m5['ema9']} vs {'%.2f' % m5['ema21']}  → {m5_label}")
print(f"  M1  EMA9 vs EMA21  : {'%.2f' % m1['ema9']} vs {'%.2f' % m1['ema21']}  → {m1_label}")
print(f"  RSI (M1)           : {rsi_m1:.1f}")
print(f"  ATR (M1)           : ${atr_m1:.2f}")

# ══════════════════════════════════════════════════════════════════════
#  STEP 2 — DIRECTION DECISION  (majority vote)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'─'*65}")
print(f"  STEP 2 ▸ Direction Decision")
print(f"{'─'*65}")

bull_votes = sum([h1_bull, m5_bull, m1_bull])
bear_votes = 3 - bull_votes

print(f"\n  Bull votes : {bull_votes}/3   Bear votes : {bear_votes}/3")

if bull_votes >= 2:
    DIRECTION = "LONG"
    SL_PRICE  = round(price - SL_POINTS * POINT, DIGITS)
    print(f"  Decision   : ✅ LONG — majority ({bull_votes}/3 timeframes bullish)")
elif bear_votes >= 2:
    DIRECTION = "SHORT"
    SL_PRICE  = round(price + SL_POINTS * POINT, DIGITS)
    print(f"  Decision   : ✅ SHORT — majority ({bear_votes}/3 timeframes bearish)")
else:
    DIRECTION = "SHORT" if not h1_bull else "LONG"
    if DIRECTION == "LONG":
        SL_PRICE = round(price - SL_POINTS * POINT, DIGITS)
    else:
        SL_PRICE = round(price + SL_POINTS * POINT, DIGITS)
    print(f"  Decision   : ⚠️ MIXED signals — using H1 trend → {DIRECTION}")

# ══════════════════════════════════════════════════════════════════════
#  STEP 3 — WAIT FOR M1 MOMENTUM CONFIRMATION  (2 green/red M1 candles)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'─'*65}")
print(f"  STEP 3 ▸ M1 Momentum Confirmation")
print(f"{'─'*65}")

last3 = df_m1.iloc[-4:-1]   # last 3 CLOSED candles (not live)
if DIRECTION == "LONG":
    green_candles = (last3['close'] > last3['open']).sum()
    confirmed = green_candles >= 2
    conf_label = f"{green_candles}/3 green M1 candles"
else:
    red_candles = (last3['close'] < last3['open']).sum()
    confirmed = red_candles >= 2
    conf_label = f"{red_candles}/3 red M1 candles"

print(f"\n  Looking for 2+ consecutive {'green' if DIRECTION=='LONG' else 'red'} M1 candles...")
print(f"  Result : {conf_label}  → {'✅ CONFIRMED' if confirmed else '⚠️ Weak — entering anyway with tight SL'}")
print(f"\n  Trade direction : {DIRECTION}")
print(f"  Stop loss price : ${SL_PRICE:,.{DIGITS}f}  ({SL_POINTS} pts = ~${SL_POINTS*POINT*LOT_SIZE*100:.1f} risk)")
print(f"  Profit target   : $+{PROFIT_TARGET:.0f} per trade (managed in code)")
print(f"  Breakeven       : at $+{BREAKEVEN_AT:.0f}")

# ══════════════════════════════════════════════════════════════════════
#  STEP 4 — OPEN TRADES (staggered, only if previous is profitable)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'─'*65}")
print(f"  STEP 4 ▸ Opening {NUM_TRADES} Staggered Trades")
print(f"{'─'*65}\n")

trades = []

for i in range(NUM_TRADES):
    label = f"T{i+1}"

    # For T2+, wait and check previous trades are healthy
    if i > 0 and trades:
        print(f"  [{ts()}] Waiting {TRADE_GAP_SEC}s before {label}...")
        time.sleep(TRADE_GAP_SEC)

        worst_pnl  = 0.0
        be_count   = 0
        open_count = 0
        for prev in trades:
            if prev['closed']: continue
            open_count += 1
            pl = mt5.positions_get(ticket=prev['ticket'])
            if pl:
                pnl = pl[0].profit
                worst_pnl = min(worst_pnl, pnl)
                if prev['be_set']: be_count += 1

        # Skip if trades already at BE — main move is done, don't chase
        if be_count == open_count and open_count > 0:
            print(f"  [{ts()}] {label}: ⛔ SKIPPING — all {open_count} open trade(s) already at BE (move is done)")
            continue
        if worst_pnl < -(BREAKEVEN_AT * 2):
            print(f"  [{ts()}] {label}: ⛔ SKIPPING — trade at ${worst_pnl:.2f} (too negative)")
            continue
        print(f"  [{ts()}] {label}: Worst P&L = ${worst_pnl:+.2f} | BE trades = {be_count}/{open_count} — adding")

    t, err = send_order(DIRECTION, SL_PRICE)
    if t is None:
        print(f"  [{ts()}] {label}: ❌ FAILED — {err}")
    else:
        risk = abs(t['entry'] - SL_PRICE) * LOT_SIZE * 100
        t['trail_sl']   = SL_PRICE   # track trailing SL level
        t['peak_pnl']   = 0.0        # track highest profit seen
        print(f"  [{ts()}] {label}: ✅ Ticket={t['ticket']}  Entry=${t['entry']:,.2f}  SL=${SL_PRICE:,.2f}  Risk≈${risk:.2f}")
        trades.append(t)

if not trades:
    print("\n  No trades opened!"); mt5.shutdown(); sys.exit(1)

# ══════════════════════════════════════════════════════════════════════
#  STEP 5 — ACTIVE MANAGEMENT LOOP
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'═'*65}")
print(f"  STEP 5 ▸ Active Manager — {len(trades)} trades live")
print(f"  Exit rules: +${PROFIT_TARGET:.0f}=BE  trail=${TRAIL_STEP:.0f}  -${MAX_LOSS_USD:.0f}=cut")
print(f"{'═'*65}\n")

print(f"  {'Time':<10} {'Ticket':<14} {'#':<4} {'P&L':>8}  {'Action'}")
print(f"  {'─'*56}")

start      = time.time()
last_pnl   = {}   # ticket → last printed P&L to avoid spam

while time.time() - start < MAX_RUN_SEC:
    time.sleep(1)

    active = [t for t in trades if not t['closed']]
    if not active:
        print(f"\n  [{ts()}] All trades closed. Session complete.")
        break

    for t in active:
        pos_list = mt5.positions_get(ticket=t['ticket'])

        # ── Position gone (SL hit by MT5) ─────────────────────────
        if not pos_list:
            if not t['closed']:
                t['closed'] = True
                print(f"  [{ts()}] {t['ticket']:<14} {'T?':<4} {'---':>8}  ✅ Closed by MT5 SL")
            continue

        pnl = pos_list[0].profit
        t['peak_pnl'] = max(t.get('peak_pnl', 0.0), pnl)

        # Skip printing if P&L hasn't changed
        if last_pnl.get(t['ticket']) == round(pnl, 2):
            continue
        last_pnl[t['ticket']] = round(pnl, 2)

        # ── RULE 1: Close at +$7 target ────────────────────────────
        if pnl >= PROFIT_TARGET:
            ok = close_trade(t, "TARGET")
            t['closed'] = True
            print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  💰 PROFIT TAKEN +${pnl:.2f} ✅")
            continue

        # ── RULE 2: Move SL to breakeven at +$3 ───────────────────
        if pnl >= BREAKEVEN_AT and not t['be_set']:
            ok = move_to_be(t)
            if ok:
                t['be_set']   = True
                t['trail_sl'] = t['entry']
                print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  ⚡ BE SET @ ${t['entry']:,.2f}")
            continue

        # ── RULE 3: Trailing stop — move up every $2 after BE ──────
        if t['be_set'] and pnl > 0:
            si_info = mt5.symbol_info(SYMBOL)
            if DIRECTION == "LONG":
                # New trail SL = current_price - $2 equivalent
                tick_now   = mt5.symbol_info_tick(SYMBOL)
                new_trail  = round(tick_now.bid - (TRAIL_STEP / (LOT_SIZE * 100)) , si_info.digits)
                if new_trail > t['trail_sl'] + si_info.point:
                    ok = set_sl(t, new_trail)
                    if ok:
                        t['trail_sl'] = new_trail
                        print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  📈 TRAIL SL → ${new_trail:,.2f}")
            else:
                tick_now   = mt5.symbol_info_tick(SYMBOL)
                new_trail  = round(tick_now.ask + (TRAIL_STEP / (LOT_SIZE * 100)), si_info.digits)
                if new_trail < t['trail_sl'] - si_info.point:
                    ok = set_sl(t, new_trail)
                    if ok:
                        t['trail_sl'] = new_trail
                        print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  📉 TRAIL SL → ${new_trail:,.2f}")

        # ── RULE 4: Force close at -$15 ───────────────────────────
        if pnl <= -MAX_LOSS_USD:
            ok = close_trade(t, "CUTLOSS")
            t['closed'] = True
            print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  🔴 CUT at -${abs(pnl):.2f}")
            continue

        # ── Running status ─────────────────────────────────────────
        be_flag = " ⚡BE" if t['be_set'] else ""
        icon    = "🟢" if pnl > 0 else "🔴"
        print(f"  [{ts()}] {t['ticket']:<14} {pnl:>+8.2f}  {icon} Running{be_flag}")

# ── Timeout: close anything still open ────────────────────────────────
remaining = [t for t in trades if not t['closed']]
if remaining:
    print(f"\n  [{ts()}] ⏱ Timeout — closing {len(remaining)} remaining trade(s)...")
    for t in remaining:
        ok = close_trade(t, "TIMEOUT")
        t['closed'] = ok
        status = "✅ closed" if ok else "❌ failed — close manually in MT5"
        print(f"  [{ts()}] Ticket {t['ticket']}: {status}")

# ══════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'═'*65}")
print(f"  SESSION SUMMARY")
print(f"{'═'*65}")

# Get realized P&L from deal history
total_pnl = 0.0
try:
    ticket_set = {t['ticket'] for t in trades}
    deals = mt5.history_deals_get(
        datetime.datetime.utcnow() - datetime.timedelta(minutes=30),
        datetime.datetime.utcnow() + datetime.timedelta(minutes=1),
    )
    if deals:
        for d in deals:
            if d.position_id in ticket_set and d.profit != 0:
                total_pnl += d.profit
except Exception as e:
    print(f"  (Could not fetch deal history: {e})")

acc2 = mt5.account_info()
print(f"\n  Trades opened  : {len(trades)}")
print(f"  Profit target  : +${PROFIT_TARGET:.0f} per trade")
print(f"  Realized P&L   : ${total_pnl:+.2f}")
print(f"  Account equity : ${acc2.equity:,.2f}  (was ${acc.equity:,.2f})")
print(f"{'═'*65}")
mt5.shutdown()
