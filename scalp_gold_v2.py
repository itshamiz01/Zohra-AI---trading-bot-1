"""
XAUUSD Gold Scalper v2 — PROPER SCALPING
=========================================
Rules:
  - Enter in trend direction (EMA9/21 on M1)
  - Close ENTIRE trade when profit >= +$10  ← QUICK EXIT
  - Move SL to breakeven when profit >= +$5  ← PROTECT CAPITAL
  - Hard cut if loss reaches -$15            ← TIGHT RISK
  - No big ATR targets — in and OUT fast
"""
import os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ── SCALPING CONFIG ───────────────────────────────────────────────────
SYMBOL         = "XAUUSD"
LOT_SIZE       = 0.10          # 0.10 lots per trade
NUM_TRADES     = 4             # Number of scalp trades
TF             = mt5.TIMEFRAME_M1   # M1 — scalping uses 1-minute chart
EMA_FAST       = 9
EMA_SLOW       = 21
MAGIC          = 20240301

# ── KEY SCALPING RULES ────────────────────────────────────────────────
PROFIT_CLOSE_USD   = 10.0    # Close trade when profit >= $10
BREAKEVEN_USD      = 5.0     # Move SL to breakeven when profit >= $5
MAX_LOSS_USD       = 15.0    # Hard cut loss per trade at -$15
INITIAL_SL_POINTS  = 150     # Initial SL = 150 points ($1.50 move) — very tight
MONITOR_INTERVAL   = 1       # Check every 1 second (active scalp management)
MAX_MONITOR_SECS   = 300     # Run manager for up to 5 minutes

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# ─────────────────────────────────────────────────────────────────────
print("=" * 65)
print("   XAUUSD GOLD SCALPER v2 — Proper Scalping Mode")
print("   Target: +$10 per trade | Breakeven at +$5 | Cut at -$15")
print("=" * 65)

if not mt5.initialize():
    print(f"FAILED to init MT5: {mt5.last_error()}"); sys.exit(1)

if not mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print(f"FAILED login: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

acc = mt5.account_info()
print(f"\n  Account  : {acc.name}")
print(f"  Balance  : ${acc.balance:,.2f}")
print(f"  Equity   : ${acc.equity:,.2f}")

if not mt5.symbol_select(SYMBOL, True):
    print(f"FAILED: {SYMBOL} not available!"); mt5.shutdown(); sys.exit(1)

si = mt5.symbol_info(SYMBOL)
digits = si.digits
point  = si.point   # e.g. 0.01 for Gold

LOT_SIZE = max(si.volume_min, min(LOT_SIZE, si.volume_max))
LOT_SIZE = round(round(LOT_SIZE / si.volume_step) * si.volume_step, 2)

# ── Get M1 candles for trend ──────────────────────────────────────────
print(f"\n[1/3] Fetching {SYMBOL} M1 candles for scalp trend...")
rates = mt5.copy_rates_from_pos(SYMBOL, TF, 0, 100)
if rates is None or len(rates) < 30:
    print("Failed to get M1 data!"); mt5.shutdown(); sys.exit(1)

df = pd.DataFrame(rates)
df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()

# ATR on M1
df['tr'] = np.maximum(
    df['high'] - df['low'],
    np.maximum(abs(df['high'] - df['close'].shift(1)),
               abs(df['low']  - df['close'].shift(1)))
)
df['atr'] = df['tr'].rolling(14).mean()

last     = df.iloc[-1]
atr_m1   = last['atr']
ema_fast = last['ema_fast']
ema_slow = last['ema_slow']

# Direction
if ema_fast >= ema_slow:
    direction  = "LONG"
    order_type = mt5.ORDER_TYPE_BUY
    trend_txt  = "BULLISH (EMA9 >= EMA21 on M1)"
else:
    direction  = "SHORT"
    order_type = mt5.ORDER_TYPE_SELL
    trend_txt  = "BEARISH (EMA9 < EMA21 on M1)"

print(f"[2/3] Trend Analysis:")
print(f"  EMA9    : ${ema_fast:,.2f}")
print(f"  EMA21   : ${ema_slow:,.2f}")
print(f"  ATR M1  : ${atr_m1:.2f}")
print(f"  Trend   : {trend_txt}")
print(f"  Direction: {direction}")

# ── Filling mode ──────────────────────────────────────────────────────
def get_filling(sym):
    info = mt5.symbol_info(sym)
    if info is None: return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 4: return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK

filling = get_filling(SYMBOL)

# ── Close position helper ─────────────────────────────────────────────
def close_position(ticket, symbol, vol, pos_type, reason=""):
    tick = mt5.symbol_info_tick(symbol)
    if pos_type == 0:   # BUY → close with SELL
        close_type = mt5.ORDER_TYPE_SELL
        price      = tick.bid
    else:               # SELL → close with BUY
        close_type = mt5.ORDER_TYPE_BUY
        price      = tick.ask

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       vol,
        "type":         close_type,
        "position":     ticket,
        "price":        price,
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"Scalp_Close_{reason}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling(symbol),
    }
    result = mt5.order_send(req)
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

def modify_sl(ticket, symbol, new_sl):
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    pos = positions[0]
    req = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   symbol,
        "position": ticket,
        "sl":       round(new_sl, digits),
        "tp":       pos.tp,
    }
    result = mt5.order_send(req)
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

# ── Open 4 Scalp Trades ───────────────────────────────────────────────
print(f"\n[3/3] Opening {NUM_TRADES} scalp trades...")
print("=" * 65)
print(f"  Mode     : SCALP — close at +${PROFIT_CLOSE_USD:.0f} | BE at +${BREAKEVEN_USD:.0f} | Cut at -${MAX_LOSS_USD:.0f}")
print(f"  Lots     : {LOT_SIZE} per trade")
print(f"  Initial SL: {INITIAL_SL_POINTS} pts (${INITIAL_SL_POINTS * point * 100 * LOT_SIZE:.2f} risk per trade)")
print()

opened = []  # list of {ticket, entry, pos_type, sl, be_set}

for i in range(NUM_TRADES):
    tick = mt5.symbol_info_tick(SYMBOL)

    if direction == "LONG":
        entry    = tick.ask
        sl_price = round(entry - INITIAL_SL_POINTS * point, digits)
    else:
        entry    = tick.bid
        sl_price = round(entry + INITIAL_SL_POINTS * point, digits)

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       LOT_SIZE,
        "type":         order_type,
        "price":        entry,
        "sl":           sl_price,
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"GoldScalp_v2_T{i+1}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(req)

    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        retcode = result.retcode if result else "None"
        comment = result.comment if result else str(mt5.last_error())
        print(f"  Trade {i+1}/{NUM_TRADES}: ❌ FAILED  retcode={retcode} — {comment}")
    else:
        fill = result.price if result.price else entry
        opened.append({
            "ticket":   result.order,
            "entry":    fill,
            "pos_type": 0 if direction == "LONG" else 1,
            "sl":       sl_price,
            "be_set":   False,
            "closed":   False,
            "label":    f"T{i+1}",
        })
        print(f"  Trade {i+1}/{NUM_TRADES}: ✅ OPENED  Ticket={result.order}  Entry=${fill:,.2f}  SL=${sl_price:,.2f}")

    time.sleep(0.2)

if not opened:
    print("\nNo trades opened. Exiting."); mt5.shutdown(); sys.exit(1)

print()
print("=" * 65)
print(f"  {len(opened)} TRADES OPEN — Active Scalp Manager Running...")
print(f"  Will auto-close at +${PROFIT_CLOSE_USD:.0f} | Move BE at +${BREAKEVEN_USD:.0f} | Cut at -${MAX_LOSS_USD:.0f}")
print("=" * 65)
print(f"\n  {'Time':<10} {'Ticket':<14} {'Trade':<5} {'P&L':>8}  {'Status'}")
print(f"  {'-'*58}")

# ── ACTIVE SCALP MANAGER LOOP ─────────────────────────────────────────
start_time   = time.time()
closed_count = 0

while time.time() - start_time < MAX_MONITOR_SECS:
    time.sleep(MONITOR_INTERVAL)
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")

    all_done = True

    for t in opened:
        if t["closed"]:
            continue

        all_done = False

        positions = mt5.positions_get(ticket=t["ticket"])
        if not positions:
            # Closed by SL or externally
            t["closed"] = True
            closed_count += 1
            print(f"  [{now}] {t['ticket']:<14} {t['label']:<5} {'---':>8}  ✅ CLOSED (SL/External)")
            continue

        pos = positions[0]
        pnl = pos.profit

        status = ""

        # ── Rule 1: Close at +$10 profit ─────────────────────────────
        if pnl >= PROFIT_CLOSE_USD:
            ok = close_position(t["ticket"], SYMBOL, pos.volume, pos.type, "PROFIT_10")
            t["closed"] = True
            closed_count += 1
            status = f"🟢 CLOSED @ +${pnl:.2f} TARGET HIT!"
            print(f"  [{now}] {t['ticket']:<14} {t['label']:<5} {pnl:>+8.2f}  {status}")
            continue

        # ── Rule 2: Move SL to breakeven at +$5 ──────────────────────
        if pnl >= BREAKEVEN_USD and not t["be_set"]:
            be_sl = round(t["entry"], digits)
            ok = modify_sl(t["ticket"], SYMBOL, be_sl)
            if ok:
                t["be_set"] = True
                t["sl"]     = be_sl
                status = f"⚡ BE SET @ ${be_sl:,.2f} | P&L: +${pnl:.2f}"
            else:
                status = f"⚠️  BE FAILED | P&L: +${pnl:.2f}"
            print(f"  [{now}] {t['ticket']:<14} {t['label']:<5} {pnl:>+8.2f}  {status}")
            continue

        # ── Rule 3: Hard cut at -$15 ──────────────────────────────────
        if pnl <= -MAX_LOSS_USD:
            ok = close_position(t["ticket"], SYMBOL, pos.volume, pos.type, "CUT_LOSS")
            t["closed"] = True
            closed_count += 1
            status = f"🔴 CUT LOSS @ -${abs(pnl):.2f}"
            print(f"  [{now}] {t['ticket']:<14} {t['label']:<5} {pnl:>+8.2f}  {status}")
            continue

        # ── Status update (every 5 iterations roughly) ────────────────
        be_tag = " [BE✅]" if t["be_set"] else ""
        status = f"{'🟢' if pnl >= 0 else '🔴'} Running {pnl:+.2f}{be_tag}"
        print(f"  [{now}] {t['ticket']:<14} {t['label']:<5} {pnl:>+8.2f}  {status}")

    if all_done:
        print(f"\n  All trades closed. Exiting manager.")
        break

# ── Final Summary ─────────────────────────────────────────────────────
print()
print("=" * 65)
print("  SCALP SESSION COMPLETE")
print("=" * 65)

# Collect any remaining open positions from this session
tickets = [t["ticket"] for t in opened]
total_closed_pnl = 0

# Check deal history for closed trades
from datetime import timedelta
import datetime as dt
deals = mt5.history_deals_get(
    dt.datetime.utcnow() - timedelta(minutes=15),
    dt.datetime.utcnow() + timedelta(minutes=1),
)
if deals:
    for d in deals:
        if d.position_id in tickets and d.profit != 0:
            total_closed_pnl += d.profit

print(f"\n  Trades Opened  : {len(opened)}")
print(f"  Trades Closed  : {closed_count}")
print(f"  Realized P&L   : ${total_closed_pnl:+.2f}")
print(f"\n  Check MT5 Trade tab for any still-open positions.")
print("=" * 65)

mt5.shutdown()
