"""
Force Trade Script
Analyzes all 5 pairs, finds the strongest trend, places a real trade.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, EMA_FAST, EMA_SLOW, ATR_PERIOD

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
TEST_LOT = 0.01

# ── Connect ──────────────────────────────────────────────────────────
print("=" * 60)
print("  FORCE TRADE — Finding Best Current Opportunity")
print("=" * 60)

if not mt5.initialize():
    print(f"FAILED to init MT5: {mt5.last_error()}")
    sys.exit(1)

if not mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print(f"FAILED login: {mt5.last_error()}")
    mt5.shutdown(); sys.exit(1)

info = mt5.account_info()
print(f"\nAccount  : {info.name}")
print(f"Balance  : ${info.balance:,.2f}")
print(f"Equity   : ${info.equity:,.2f}")
print(f"Leverage : 1:{info.leverage}")

# ── Get filling mode ─────────────────────────────────────────────────
def get_filling(symbol):
    si = mt5.symbol_info(symbol)
    if si is None: return mt5.ORDER_FILLING_FOK
    fm = si.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    if fm & 4: return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK

# ── Analyze all pairs ────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  MARKET ANALYSIS — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
print(f"{'='*60}")
print(f"\n{'Pair':<10} {'Direction':<10} {'Score':>6} {'ATR':>8} {'EMA Gap':>10} {'Signal'}")
print("-" * 60)

best = None
candidates = []

for symbol in PAIRS:
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 120)
    if rates is None or len(rates) < 60:
        print(f"{symbol:<10} {'NO DATA':<10}")
        continue

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()

    # ATR
    df['tr'] = np.maximum(df['high'] - df['low'],
               np.maximum(abs(df['high'] - df['close'].shift(1)),
                          abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(ATR_PERIOD).mean()

    # Crossover signals
    df['ema_diff'] = df['ema_fast'] - df['ema_slow']
    df['cross_up']   = (df['ema_diff'] > 0) & (df['ema_diff'].shift(1) <= 0)
    df['cross_down'] = (df['ema_diff'] < 0) & (df['ema_diff'].shift(1) >= 0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    atr      = last['atr']
    ema_gap  = abs(last['ema_fast'] - last['ema_slow'])
    price    = last['close']
    above_both = price > last['ema_fast'] and price > last['ema_slow']
    below_both = price < last['ema_fast'] and price < last['ema_slow']

    # Determine direction based on EMA alignment + crossover
    has_crossover_long  = last['cross_up']   or df['cross_up'].iloc[-5:].any()
    has_crossover_short = last['cross_down'] or df['cross_down'].iloc[-5:].any()

    if above_both and last['ema_diff'] > 0:
        direction = "LONG"
        # Score = how far above both EMAs + recent crossover bonus
        score = (ema_gap / atr) * 100
        if has_crossover_long: score += 30
        signal_type = "CROSSOVER" if has_crossover_long else "TREND"
    elif below_both and last['ema_diff'] < 0:
        direction = "SHORT"
        score = (ema_gap / atr) * 100
        if has_crossover_short: score += 30
        signal_type = "CROSSOVER" if has_crossover_short else "TREND"
    else:
        direction = "FLAT"
        score = 0
        signal_type = "NONE"

    print(f"{symbol:<10} {direction:<10} {score:>6.1f} {atr:>8.5f} {ema_gap:>10.5f}  {signal_type}")

    if direction != "FLAT" and atr > 0.0003:
        candidates.append({
            "symbol": symbol,
            "direction": direction,
            "score": score,
            "atr": atr,
            "price": price,
            "signal_type": signal_type,
        })

# ── Pick best candidate ───────────────────────────────────────────────
if not candidates:
    print("\nNo tradeable setups right now. Market is choppy across all pairs.")
    mt5.shutdown(); sys.exit(0)

candidates.sort(key=lambda x: x['score'], reverse=True)
best = candidates[0]

print(f"\n{'='*60}")
print(f"  BEST SETUP: {best['direction']} {best['symbol']}")
print(f"  Type      : {best['signal_type']}")
print(f"  Score     : {best['score']:.1f}")
print(f"  ATR       : {best['atr']:.5f}")
print(f"{'='*60}")

# ── Place the trade ───────────────────────────────────────────────────
symbol    = best['symbol']
direction = best['direction']
atr       = best['atr']

mt5.symbol_select(symbol, True)
tick = mt5.symbol_info_tick(symbol)
si   = mt5.symbol_info(symbol)
digits = si.digits if si else 5

if direction == "LONG":
    entry    = tick.ask
    sl       = round(entry - atr * 1.5, digits)
    tp       = round(entry + atr * 3.0, digits)
    otype    = mt5.ORDER_TYPE_BUY
else:
    entry    = tick.bid
    sl       = round(entry + atr * 1.5, digits)
    tp       = round(entry - atr * 3.0, digits)
    otype    = mt5.ORDER_TYPE_SELL

print(f"\nPlacing {direction} trade on {symbol}...")
print(f"  Entry  : {entry:.{digits}f}")
print(f"  SL     : {sl:.{digits}f}  ({atr*1.5:.{digits}f} = 1.5x ATR)")
print(f"  TP     : {tp:.{digits}f}  ({atr*3.0:.{digits}f} = 3.0x ATR)")
print(f"  Volume : {TEST_LOT} lots")

req = {
    "action":       mt5.TRADE_ACTION_DEAL,
    "symbol":       symbol,
    "volume":       TEST_LOT,
    "type":         otype,
    "price":        entry,
    "sl":           sl,
    "tp":           tp,
    "deviation":    20,
    "magic":        20240101,
    "comment":      "EMA_ATR_Bot",
    "type_time":    mt5.ORDER_TIME_GTC,
    "type_filling": get_filling(symbol),
}

result = mt5.order_send(req)

if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
    retcode = result.retcode if result else "None"
    comment = result.comment if result else str(mt5.last_error())
    print(f"\nTRADE FAILED! retcode={retcode}: {comment}")
    mt5.shutdown(); sys.exit(1)

ticket = result.order
fill   = result.price if result.price else entry

print(f"\n{'='*60}")
print(f"  TRADE OPENED SUCCESSFULLY!")
print(f"{'='*60}")
print(f"  Ticket     : {ticket}")
print(f"  Fill price : {fill:.{digits}f}")
print(f"  Direction  : {direction}")
print(f"  Symbol     : {symbol}")
print(f"  Volume     : {TEST_LOT} lots")
print(f"  Stop Loss  : {sl:.{digits}f}")
print(f"  Take Profit: {tp:.{digits}f}")
print(f"\n  Trade is LIVE in your MT5 account!")
print(f"  Check your MT5 terminal — you will see it in the Trades tab.")
print(f"  TP hit = +${atr*3.0*TEST_LOT*100000:.2f} profit")
print(f"  SL hit = -${atr*1.5*TEST_LOT*100000:.2f} loss")
print(f"{'='*60}")

# ── Monitor for 30 seconds ────────────────────────────────────────────
import time
print(f"\nMonitoring trade for 60 seconds...\n")
for i in range(12):
    time.sleep(5)
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        print(f"  [{i*5+5}s] Position closed (TP/SL hit or manually closed)")
        break
    pos = positions[0]
    tick2 = mt5.symbol_info_tick(symbol)
    current = tick2.bid if direction == "LONG" else tick2.ask
    pnl = pos.profit
    pip_move = (current - fill) * (10**digits) / 10 if direction == "LONG" else (fill - current) * (10**digits) / 10
    status = "PROFIT" if pnl > 0 else "LOSS"
    print(f"  [{i*5+5}s] Price: {current:.{digits}f} | P&L: ${pnl:+.2f} | Pips: {pip_move:+.1f} | {status}")

print(f"\nTrade is running. The bot will manage it automatically.")
print(f"Check MT5 terminal Trades tab for live updates.")
mt5.shutdown()
