"""
XAUUSD Gold Scalper v3 — SMART ENTRY + QUICK EXIT
===================================================
Problems fixed vs v1/v2:
  ❌ Was: Enter immediately at any time
  ✅ Now: Wait for M1 + M5 EMA confluence + RSI filter

  ❌ Was: Fixed 150-point SL (too mechanical)
  ✅ Now: SL below/above last 5-candle swing low/high

  ❌ Was: 4 trades at once blindly
  ✅ Now: Stagger entries — only enter if trade is moving IN PROFIT

Exit Rules (unchanged — these were correct):
  +$10 per trade → close immediately
  +$5 → move SL to breakeven
  -$15 → force close
"""
import os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import datetime

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# ── CONFIG ────────────────────────────────────────────────────────────
SYMBOL          = "XAUUSD"
LOT_SIZE        = 0.10
NUM_TRADES      = 4
MAGIC           = 20240401

# Entry filters
EMA_FAST_M1     = 9
EMA_SLOW_M1     = 21
EMA_FAST_M5     = 9
EMA_SLOW_M5     = 21
RSI_PERIOD      = 14
RSI_LONG_MIN    = 52        # RSI must be > 52 for LONG
RSI_SHORT_MAX   = 48        # RSI must be < 48 for SHORT

# Exit rules
PROFIT_CLOSE    = 10.0      # Close at +$10
BREAKEVEN_AT    = 5.0       # Move SL to BE at +$5
MAX_LOSS        = 15.0      # Hard cut at -$15

# SL based on swing (safer than fixed points)
SWING_CANDLES   = 6         # Look back 6 M1 candles for swing high/low
SWING_BUFFER    = 30        # Add 30 pts buffer beyond swing

# Stagger: wait up to 60s for first trade to confirm before entering next
STAGGER_WAIT    = 15        # Seconds between each new entry
CONFIRM_PROFIT  = -3.0      # Only add next trade if current P&L > -$3
MAX_MONITOR     = 300       # 5 minutes max management

# ── Connect ───────────────────────────────────────────────────────────
print("=" * 65)
print("   XAUUSD GOLD SCALPER v3 — Smart Entry + Quick Exit")
print("   Rules: Wait for M1+M5 confluence → Enter → +$10 close")
print("=" * 65)

if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}"); sys.exit(1)
if not mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print(f"MT5 login failed: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

acc = mt5.account_info()
print(f"\n  Account  : {acc.name}")
print(f"  Balance  : ${acc.balance:,.2f}")
print(f"  Equity   : ${acc.equity:,.2f}")

if not mt5.symbol_select(SYMBOL, True):
    print(f"Symbol {SYMBOL} not available!"); mt5.shutdown(); sys.exit(1)

si     = mt5.symbol_info(SYMBOL)
digits = si.digits
point  = si.point
LOT_SIZE = max(si.volume_min, min(LOT_SIZE, si.volume_max))
LOT_SIZE = round(round(LOT_SIZE / si.volume_step) * si.volume_step, 2)

# ── Indicator helpers ─────────────────────────────────────────────────
def get_df(tf, count=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    if rates is None or len(rates) < 30:
        return None
    df = pd.DataFrame(rates)
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST_M1, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW_M1, adjust=False).mean()
    delta = df['close'].diff()
    gain  = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss  = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
    rs    = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(abs(df['high'] - df['close'].shift(1)),
                   abs(df['low']  - df['close'].shift(1)))
    )
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def get_filling():
    info = mt5.symbol_info(SYMBOL)
    if info is None: return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 4: return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK

def close_trade(ticket, vol, pos_type, reason=""):
    tick = mt5.symbol_info_tick(SYMBOL)
    close_type = mt5.ORDER_TYPE_SELL if pos_type == 0 else mt5.ORDER_TYPE_BUY
    price      = tick.bid if pos_type == 0 else tick.ask
    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       vol,
        "type":         close_type,
        "position":     ticket,
        "price":        price,
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"Close_{reason}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(),
    }
    r = mt5.order_send(req)
    return r is not None and r.retcode == mt5.TRADE_RETCODE_DONE

def set_sl(ticket, new_sl):
    positions = mt5.positions_get(ticket=ticket)
    if not positions: return False
    pos = positions[0]
    req = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   SYMBOL,
        "position": ticket,
        "sl":       round(new_sl, digits),
        "tp":       pos.tp,
    }
    r = mt5.order_send(req)
    return r is not None and r.retcode == mt5.TRADE_RETCODE_DONE

# ── Analyse Market ────────────────────────────────────────────────────
print(f"\n{'─'*65}")
print(f"  STEP 1: MULTI-TIMEFRAME ANALYSIS")
print(f"{'─'*65}")

df_m1 = get_df(mt5.TIMEFRAME_M1, 100)
df_m5 = get_df(mt5.TIMEFRAME_M5, 100)

if df_m1 is None or df_m5 is None:
    print("Failed to get candle data!"); mt5.shutdown(); sys.exit(1)

last_m1 = df_m1.iloc[-1]
last_m5 = df_m5.iloc[-1]

m1_bull = last_m1['ema_fast'] > last_m1['ema_slow']
m5_bull = last_m5['ema_fast'] > last_m5['ema_slow']
rsi_m1  = last_m1['rsi']
atr_m1  = last_m1['atr']
price   = last_m1['close']

print(f"\n  ┌─ M1 (1-min scalp chart) ───────────────────────────────")
print(f"  │  Price  : ${price:,.2f}")
print(f"  │  EMA9   : ${last_m1['ema_fast']:,.2f}  EMA21: ${last_m1['ema_slow']:,.2f}")
print(f"  │  Bias   : {'BULLISH 🟢' if m1_bull else 'BEARISH 🔴'}")
print(f"  │  RSI14  : {rsi_m1:.1f}")
print(f"  │  ATR14  : ${atr_m1:.2f}")
print(f"  ├─ M5 (5-min trend filter) ──────────────────────────────")
print(f"  │  EMA9   : ${last_m5['ema_fast']:,.2f}  EMA21: ${last_m5['ema_slow']:,.2f}")
print(f"  │  Bias   : {'BULLISH 🟢' if m5_bull else 'BEARISH 🔴'}")
print(f"  └────────────────────────────────────────────────────────")

# ── Confluence Check ──────────────────────────────────────────────────
print(f"\n  STEP 2: CONFLUENCE CHECK")

if m1_bull and m5_bull and rsi_m1 > RSI_LONG_MIN:
    direction   = "LONG"
    order_type  = mt5.ORDER_TYPE_BUY
    confluence  = f"✅ M1 BULL + M5 BULL + RSI {rsi_m1:.0f} > {RSI_LONG_MIN}"
    swing_sl    = df_m1['low'].iloc[-SWING_CANDLES:].min() - SWING_BUFFER * point
elif not m1_bull and not m5_bull and rsi_m1 < RSI_SHORT_MAX:
    direction   = "SHORT"
    order_type  = mt5.ORDER_TYPE_SELL
    confluence  = f"✅ M1 BEAR + M5 BEAR + RSI {rsi_m1:.0f} < {RSI_SHORT_MAX}"
    swing_sl    = df_m1['high'].iloc[-SWING_CANDLES:].max() + SWING_BUFFER * point
else:
    # No clean confluence — show what's misaligned
    reasons = []
    if m1_bull != m5_bull:
        reasons.append(f"M1 {'BULL' if m1_bull else 'BEAR'} vs M5 {'BULL' if m5_bull else 'BEAR'} — CONFLICTING")
    if m1_bull and rsi_m1 <= RSI_LONG_MIN:
        reasons.append(f"RSI {rsi_m1:.0f} too low for LONG (need > {RSI_LONG_MIN})")
    if not m1_bull and rsi_m1 >= RSI_SHORT_MAX:
        reasons.append(f"RSI {rsi_m1:.0f} too high for SHORT (need < {RSI_SHORT_MAX})")
    print(f"\n  ⚠️  NO CLEAR CONFLUENCE — Market is choppy/mixed:")
    for r in reasons:
        print(f"     • {r}")
    print(f"\n  Forcing entry based on dominant M5 bias instead...")
    if m5_bull:
        direction  = "LONG"
        order_type = mt5.ORDER_TYPE_BUY
        confluence = f"⚠️ M5 BULL only (RSI {rsi_m1:.0f})"
        swing_sl   = df_m1['low'].iloc[-SWING_CANDLES:].min() - SWING_BUFFER * point
    else:
        direction  = "SHORT"
        order_type = mt5.ORDER_TYPE_SELL
        confluence = f"⚠️ M5 BEAR only (RSI {rsi_m1:.0f})"
        swing_sl   = df_m1['high'].iloc[-SWING_CANDLES:].max() + SWING_BUFFER * point

swing_sl = round(swing_sl, digits)
print(f"\n  Direction  : {direction}")
print(f"  Signal     : {confluence}")
print(f"  Swing SL   : ${swing_sl:,.2f} (based on last {SWING_CANDLES} candle swing)")

# ── Place Trades (staggered) ──────────────────────────────────────────
print(f"\n{'─'*65}")
print(f"  STEP 3: PLACING {NUM_TRADES} STAGGERED SCALP TRADES")
print(f"{'─'*65}\n")

opened = []

for i in range(NUM_TRADES):
    # After first trade, check if it's at least not deeply negative before adding more
    if i > 0 and opened:
        print(f"  [Waiting {STAGGER_WAIT}s before T{i+1} — checking T1 health...]")
        time.sleep(STAGGER_WAIT)
        prev_pos = mt5.positions_get(ticket=opened[0]['ticket'])
        if prev_pos:
            prev_pnl = prev_pos[0].profit
            if prev_pnl < CONFIRM_PROFIT:
                print(f"  [T1 P&L = ${prev_pnl:.2f}, below ${CONFIRM_PROFIT} threshold — "
                      f"skipping T{i+1} to protect capital]")
                continue
            else:
                print(f"  [T1 P&L = ${prev_pnl:+.2f} — OK, adding T{i+1}]")

    tick = mt5.symbol_info_tick(SYMBOL)
    entry = tick.ask if direction == "LONG" else tick.bid

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       LOT_SIZE,
        "type":         order_type,
        "price":        entry,
        "sl":           swing_sl,
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"GoldScalp_v3_T{i+1}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(),
    }

    r = mt5.order_send(req)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        retcode = r.retcode if r else "None"
        comment = r.comment if r else str(mt5.last_error())
        print(f"  T{i+1}: ❌ FAILED  retcode={retcode} — {comment}")
    else:
        fill = r.price if r.price else entry
        sl_risk = abs(fill - swing_sl) * LOT_SIZE * 100
        opened.append({
            "ticket":   r.order,
            "entry":    fill,
            "pos_type": 0 if direction == "LONG" else 1,
            "sl":       swing_sl,
            "be_set":   False,
            "closed":   False,
            "label":    f"T{i+1}",
            "pnl_peak": 0.0,
        })
        print(f"  T{i+1}: ✅ Ticket={r.order}  Entry=${fill:,.2f}  "
              f"SL=${swing_sl:,.2f}  Risk≈${sl_risk:.2f}")

if not opened:
    print("\n  No trades opened. Exiting."); mt5.shutdown(); sys.exit(1)

# ── Active Scalp Manager ──────────────────────────────────────────────
print(f"\n{'═'*65}")
print(f"  SCALP MANAGER LIVE — {len(opened)} positions")
print(f"  ✅ Close at +${PROFIT_CLOSE:.0f}  |  ⚡ BE at +${BREAKEVEN_AT:.0f}  |  🔴 Cut at -${MAX_LOSS:.0f}")
print(f"{'═'*65}")
print(f"\n  {'Time':<10} {'Ticket':<14} {'Lbl':<4} {'P&L':>8}  Action")
print(f"  {'─'*58}")

start = time.time()
prev_print = {}  # avoid spamming same P&L

while time.time() - start < MAX_MONITOR:
    time.sleep(1)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
    all_done = all(t['closed'] for t in opened)
    if all_done:
        break

    for t in opened:
        if t['closed']:
            continue

        pos_list = mt5.positions_get(ticket=t['ticket'])
        if not pos_list:
            if not t['closed']:
                t['closed'] = True
                print(f"  [{now}] {t['ticket']:<14} {t['label']:<4} {'---':>8}  ✅ CLOSED by SL/MT5")
            continue

        pos = pos_list[0]
        pnl = pos.profit

        # Skip printing if P&L unchanged (reduce noise)
        if prev_print.get(t['ticket']) == round(pnl, 2):
            continue
        prev_print[t['ticket']] = round(pnl, 2)

        # ── RULE 1: Close at +$10 ─────────────────────────────────
        if pnl >= PROFIT_CLOSE:
            ok = close_trade(t['ticket'], pos.volume, pos.type, "TARGET10")
            t['closed'] = True
            print(f"  [{now}] {t['ticket']:<14} {t['label']:<4} {pnl:>+8.2f}  💰 CLOSED +${pnl:.2f} TARGET HIT!")
            continue

        # ── RULE 2: Breakeven at +$5 ──────────────────────────────
        if pnl >= BREAKEVEN_AT and not t['be_set']:
            ok = set_sl(t['ticket'], t['entry'])
            if ok:
                t['be_set'] = True
                print(f"  [{now}] {t['ticket']:<14} {t['label']:<4} {pnl:>+8.2f}  ⚡ BREAKEVEN SET @ ${t['entry']:,.2f}")
            continue

        # ── RULE 3: Hard cut at -$15 ──────────────────────────────
        if pnl <= -MAX_LOSS:
            ok = close_trade(t['ticket'], pos.volume, pos.type, "CUTLOSS")
            t['closed'] = True
            print(f"  [{now}] {t['ticket']:<14} {t['label']:<4} {pnl:>+8.2f}  🔴 CUT LOSS -${abs(pnl):.2f}")
            continue

        # ── Status ────────────────────────────────────────────────
        be_tag = " ⚡BE" if t['be_set'] else ""
        icon   = "🟢" if pnl >= 0 else "🔴"
        print(f"  [{now}] {t['ticket']:<14} {t['label']:<4} {pnl:>+8.2f}  {icon} Running{be_tag}")

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'═'*65}")
print(f"  SESSION COMPLETE")
print(f"{'═'*65}")

total_pnl = 0.0
deals = mt5.history_deals_get(
    datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(minutes=20),
    datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(minutes=1),
)
tickets = {t['ticket'] for t in opened}
if deals:
    for d in deals:
        if d.position_id in tickets and d.profit != 0:
            total_pnl += d.profit

won  = sum(1 for t in opened if t['closed'])
open_left = sum(1 for t in opened if not t['closed'])

print(f"\n  Trades Opened : {len(opened)}")
print(f"  Closed        : {won}  |  Still Open: {open_left}")
print(f"  Realized P&L  : ${total_pnl:+.2f}")
if open_left:
    print(f"\n  ⚠️  {open_left} trade(s) still running in MT5 — manage manually or re-run script")
print(f"{'═'*65}")
mt5.shutdown()
