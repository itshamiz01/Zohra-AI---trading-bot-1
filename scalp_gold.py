"""
XAUUSD (Gold) Scalping Bot
Places 4-5 trades using M5 EMA + RSI momentum on Gold.
Big lots, tight stops, quick targets.
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

# ── CONFIG ────────────────────────────────────────────────────────────
SYMBOL     = "XAUUSD"
LOT_SIZE   = 0.10          # 0.10 lots per trade (bigger size on $100k account)
NUM_TRADES = 4             # Number of scalp trades to place
TF         = mt5.TIMEFRAME_M5   # M5 scalping timeframe
EMA_FAST   = 9
EMA_SLOW   = 21
RSI_PERIOD = 14
ATR_SL_MULT  = 0.8         # Tight SL for scalping
ATR_TP_MULT  = [1.5, 2.0, 2.5, 3.0]   # Each trade has a different TP target
MAGIC      = 20240201

# ── Connect ───────────────────────────────────────────────────────────
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

print("=" * 65)
print("   XAUUSD GOLD SCALPER — 4-Trade Ladder Strategy")
print("=" * 65)

if not mt5.initialize():
    print(f"FAILED to init MT5: {mt5.last_error()}"); sys.exit(1)

if not mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print(f"FAILED login: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

acc = mt5.account_info()
print(f"\n  Account : {acc.name}")
print(f"  Balance : ${acc.balance:,.2f}")
print(f"  Equity  : ${acc.equity:,.2f}")
print(f"  Leverage: 1:{acc.leverage}")

# ── Enable XAUUSD ─────────────────────────────────────────────────────
if not mt5.symbol_select(SYMBOL, True):
    print(f"\nFAILED: {SYMBOL} not available in this broker!"); mt5.shutdown(); sys.exit(1)

si = mt5.symbol_info(SYMBOL)
print(f"\n  Symbol  : {SYMBOL}")
print(f"  Digits  : {si.digits}")
print(f"  Spread  : {si.spread} pts")
print(f"  Min lot : {si.volume_min}")
print(f"  Max lot : {si.volume_max}")

# Clamp lot to broker limits
LOT_SIZE = max(si.volume_min, min(LOT_SIZE, si.volume_max))
LOT_SIZE = round(round(LOT_SIZE / si.volume_step) * si.volume_step, 2)

# ── Fetch M5 candles ──────────────────────────────────────────────────
print(f"\n[1/4] Fetching {SYMBOL} M5 candles...")
rates = mt5.copy_rates_from_pos(SYMBOL, TF, 0, 200)
if rates is None or len(rates) < 50:
    print(f"Failed to get candle data: {mt5.last_error()}"); mt5.shutdown(); sys.exit(1)

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

# ── Indicators ────────────────────────────────────────────────────────
print("[2/4] Calculating indicators (EMA9/21 + RSI14 + ATR)...")

df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()

# RSI
delta  = df['close'].diff()
gain   = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
loss   = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
rs     = gain / loss.replace(0, np.nan)
df['rsi'] = 100 - (100 / (1 + rs))

# ATR
df['tr'] = np.maximum(
    df['high'] - df['low'],
    np.maximum(abs(df['high'] - df['close'].shift(1)),
               abs(df['low']  - df['close'].shift(1)))
)
df['atr'] = df['tr'].rolling(14).mean()

last = df.iloc[-1]
prev = df.iloc[-2]

atr       = last['atr']
ema_fast  = last['ema_fast']
ema_slow  = last['ema_slow']
rsi       = last['rsi']
close     = last['close']

# ── Determine Direction ───────────────────────────────────────────────
print("[3/4] Analysing trend & momentum...")
print()
print(f"  Current Price : ${close:,.2f}")
print(f"  EMA9          : ${ema_fast:,.2f}")
print(f"  EMA21         : ${ema_slow:,.2f}")
print(f"  RSI(14)       : {rsi:.1f}")
print(f"  ATR(14) M5    : ${atr:.2f}")
print()

# Direction logic: EMA alignment + RSI momentum
if ema_fast > ema_slow and rsi > 50:
    direction = "LONG"
    trend_str = "BULLISH (EMA9 > EMA21, RSI > 50)"
elif ema_fast < ema_slow and rsi < 50:
    direction = "SHORT"
    trend_str = "BEARISH (EMA9 < EMA21, RSI < 50)"
elif ema_fast > ema_slow:
    direction = "LONG"
    trend_str = "BULLISH (EMA9 > EMA21)"
else:
    direction = "SHORT"
    trend_str = "BEARISH (EMA9 < EMA21)"

print(f"  Trend         : {trend_str}")
print(f"  Direction     : {direction}")

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
digits  = si.digits

# ── Place 4 Trades ────────────────────────────────────────────────────
print()
print("=" * 65)
print(f"  PLACING {NUM_TRADES} SCALP TRADES — {direction} XAUUSD")
print("=" * 65)

tick = mt5.symbol_info_tick(SYMBOL)
if direction == "LONG":
    base_entry = tick.ask
    sl_price   = round(base_entry - atr * ATR_SL_MULT, digits)
    order_type = mt5.ORDER_TYPE_BUY
else:
    base_entry = tick.bid
    sl_price   = round(base_entry + atr * ATR_SL_MULT, digits)
    order_type = mt5.ORDER_TYPE_SELL

print(f"\n  Base Entry : ${base_entry:,.{digits}f}")
print(f"  Stop Loss  : ${sl_price:,.{digits}f}  (ATR x{ATR_SL_MULT} = ${atr*ATR_SL_MULT:.2f})")
print(f"  Lot Size   : {LOT_SIZE} lots each")
print()

opened_trades = []

for i in range(NUM_TRADES):
    tp_mult = ATR_TP_MULT[i]
    tick    = mt5.symbol_info_tick(SYMBOL)  # refresh tick each time

    if direction == "LONG":
        entry = tick.ask
        tp    = round(entry + atr * tp_mult, digits)
    else:
        entry = tick.bid
        tp    = round(entry - atr * tp_mult, digits)

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       LOT_SIZE,
        "type":         order_type,
        "price":        entry,
        "sl":           sl_price,
        "tp":           tp,
        "deviation":    30,
        "magic":        MAGIC,
        "comment":      f"GoldScalp_T{i+1}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(req)

    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        retcode = result.retcode if result else "None"
        comment = result.comment if result else str(mt5.last_error())
        print(f"  Trade {i+1}/{NUM_TRADES}: FAILED  retcode={retcode} — {comment}")
    else:
        ticket     = result.order
        fill_price = result.price if result.price else entry
        profit_tgt = abs(tp - fill_price) * LOT_SIZE * 100  # approx USD (Gold = $100/pt/lot)
        loss_risk  = abs(sl_price - fill_price) * LOT_SIZE * 100

        opened_trades.append({
            "ticket": ticket, "entry": fill_price,
            "sl": sl_price, "tp": tp,
            "tp_mult": tp_mult, "lot": LOT_SIZE
        })

        print(f"  Trade {i+1}/{NUM_TRADES}: ✅ OPENED  Ticket={ticket}")
        print(f"    Entry : ${fill_price:,.{digits}f}")
        print(f"    SL    : ${sl_price:,.{digits}f}  (risk ≈ ${loss_risk:.2f})")
        print(f"    TP    : ${tp:,.{digits}f}  (target ≈ +${profit_tgt:.2f}, TP mult={tp_mult}x ATR)")
        print()

    time.sleep(0.3)   # small pause between orders

# ── Summary ───────────────────────────────────────────────────────────
print("=" * 65)
print(f"  {len(opened_trades)}/{NUM_TRADES} TRADES OPENED SUCCESSFULLY")
print("=" * 65)

if opened_trades:
    total_risk   = sum(abs(t['sl'] - t['entry']) * t['lot'] * 100 for t in opened_trades)
    total_reward = sum(abs(t['tp'] - t['entry']) * t['lot'] * 100 for t in opened_trades)
    print(f"\n  Total Risk   : ~${total_risk:.2f}")
    print(f"  Total Reward : ~${total_reward:.2f}")
    print(f"  Combined R/R : {total_reward/total_risk:.1f}:1" if total_risk > 0 else "")
    print(f"\n  Tickets: {[t['ticket'] for t in opened_trades]}")

# ── Live Monitor — 90 seconds ─────────────────────────────────────────
print(f"\n{'─'*65}")
print(f"  LIVE MONITOR — 90 seconds (updates every 5s)")
print(f"{'─'*65}\n")

tickets = [t['ticket'] for t in opened_trades]

for tick_i in range(18):
    time.sleep(5)
    now       = datetime.now(timezone.utc).strftime("%H:%M:%S")
    tick_data = mt5.symbol_info_tick(SYMBOL)
    cur_price = tick_data.bid if direction == "LONG" else tick_data.ask

    total_pnl = 0
    active     = 0
    closed     = 0

    for t in opened_trades:
        positions = mt5.positions_get(ticket=t['ticket'])
        if positions:
            pnl = positions[0].profit
            total_pnl += pnl
            active += 1
        else:
            closed += 1

    status = "🟢 PROFIT" if total_pnl > 0 else "🔴 LOSS"
    print(f"  [{now}] Gold: ${cur_price:,.2f} | Combined P&L: ${total_pnl:+.2f} | "
          f"Open: {active} | Closed(TP/SL): {closed} | {status}")

    if active == 0:
        print(f"\n  All positions closed (TP/SL hit).")
        break

print(f"\n{'='*65}")
print(f"  Done. Check MT5 Trades tab for live positions.")
print(f"{'='*65}")
mt5.shutdown()
