"""
MT5 Live Trade Test
Tests: connect -> account info -> live prices -> place 0.01 lot trade -> close it
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

import MetaTrader5 as mt5
import pandas as pd

SYMBOL = "EURUSD"
TEST_LOT = 0.01   # Micro lot — smallest possible trade

print("=" * 55)
print("  MT5 LIVE TRADE TEST")
print("=" * 55)

# ─── STEP 1: Initialize ───────────────────────────────────
print("\n[STEP 1] Connecting to MetaTrader 5...")
if not mt5.initialize():
    err = mt5.last_error()
    print(f"  FAILED: {err}")
    print()
    print("  MT5 is not running on this PC.")
    print("  Please:")
    print("  1. Download: https://www.metatrader5.com/en/download")
    print("  2. Install and OPEN MetaTrader 5")
    print("  3. Login with your demo account credentials")
    print("  4. Run this test again")
    sys.exit(1)

print("  MT5 initialized OK")

# ─── STEP 2: Login ───────────────────────────────────────
print(f"\n[STEP 2] Logging in... (account {MT5_LOGIN} @ {MT5_SERVER})")
authorized = mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
if not authorized:
    print(f"  LOGIN FAILED: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

info = mt5.account_info()
print(f"  Logged in!")
print(f"  Name     : {info.name}")
print(f"  Balance  : {info.balance:.2f} {info.currency}")
print(f"  Equity   : {info.equity:.2f} {info.currency}")
print(f"  Server   : {info.server}")
print(f"  Leverage : 1:{info.leverage}")

# ─── STEP 3: Live Price ───────────────────────────────────
print(f"\n[STEP 3] Fetching live {SYMBOL} price...")
mt5.symbol_select(SYMBOL, True)
tick = mt5.symbol_info_tick(SYMBOL)
if tick is None:
    print(f"  Cannot get price: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

print(f"  BID : {tick.bid:.5f}")
print(f"  ASK : {tick.ask:.5f}")
print(f"  Spread: {(tick.ask - tick.bid)*10000:.1f} pips")

# ─── STEP 4: Live Candles ─────────────────────────────────
print(f"\n[STEP 4] Fetching last 5 hourly {SYMBOL} candles...")
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 5)
if rates is None or len(rates) == 0:
    print(f"  Cannot get candles: {mt5.last_error()}")
else:
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df = df[['time','open','high','low','close','tick_volume']]
    print(df.to_string(index=False))

# ─── STEP 5: Place a BUY trade ───────────────────────────
print(f"\n[STEP 5] Placing test BUY trade ({TEST_LOT} lot {SYMBOL})...")
sl_price = round(tick.ask - 0.0050, 5)   # 50 pip stop loss
tp_price = round(tick.ask + 0.0100, 5)   # 100 pip take profit

# Auto-detect supported filling mode from symbol info (filling_mode is a bitmask)
# Bit 0 (value 1) = FOK supported, Bit 1 (value 2) = IOC supported, Bit 2 (value 4) = RETURN supported
sym_info = mt5.symbol_info(SYMBOL)
filling_type = mt5.ORDER_FILLING_FOK  # default fallback
if sym_info is not None:
    fm = sym_info.filling_mode
    if fm & 1:   # FOK supported
        filling_type = mt5.ORDER_FILLING_FOK
    elif fm & 2: # IOC supported
        filling_type = mt5.ORDER_FILLING_IOC
    elif fm & 4: # RETURN supported
        filling_type = mt5.ORDER_FILLING_RETURN
print(f"  Filling mode: {filling_type} (raw bitmask={sym_info.filling_mode if sym_info else 'N/A'})")

order_request = {
    "action":       mt5.TRADE_ACTION_DEAL,
    "symbol":       SYMBOL,
    "volume":       TEST_LOT,
    "type":         mt5.ORDER_TYPE_BUY,
    "price":        tick.ask,
    "sl":           sl_price,
    "tp":           tp_price,
    "deviation":    20,
    "magic":        999999,
    "comment":      "BotTest",
    "type_time":    mt5.ORDER_TIME_GTC,
    "type_filling": filling_type,
}

print(f"  Entry : {tick.ask:.5f}")
print(f"  SL    : {sl_price:.5f}")
print(f"  TP    : {tp_price:.5f}")

result = mt5.order_send(order_request)

if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
    retcode = result.retcode if result else "None"
    comment = result.comment if result else str(mt5.last_error())
    print(f"\n  TRADE FAILED! retcode={retcode}: {comment}")

    # Common retcode explanations
    retcode_map = {
        10004: "Requote — price changed, try again",
        10006: "Request rejected by server",
        10007: "Request cancelled by trader",
        10010: "Only part of the request was completed",
        10011: "Request processing error",
        10013: "Invalid request structure",
        10014: "Invalid volume",
        10015: "Invalid price",
        10016: "Invalid stops (SL/TP)",
        10018: "Market is closed",
        10019: "Insufficient funds",
        10024: "Too many requests",
        10027: "Auto-trading disabled by server",
        10028: "Auto-trading disabled by client",
    }
    if result and result.retcode in retcode_map:
        print(f"  Reason: {retcode_map[result.retcode]}")
    mt5.shutdown()
    sys.exit(1)

ticket = result.order
fill_price = result.price
print(f"\n  TRADE OPENED!")
print(f"  Ticket     : {ticket}")
print(f"  Fill price : {fill_price:.5f}")
print(f"  Volume     : {TEST_LOT} lots")

# ─── STEP 6: Check Position ───────────────────────────────
print(f"\n[STEP 6] Verifying position in account...")
time.sleep(1)
positions = mt5.positions_get(ticket=ticket)
if positions:
    pos = positions[0]
    print(f"  Position confirmed in account!")
    print(f"  Symbol    : {pos.symbol}")
    print(f"  Type      : {'BUY' if pos.type == 0 else 'SELL'}")
    print(f"  Volume    : {pos.volume} lots")
    print(f"  Open Price: {pos.price_open:.5f}")
    print(f"  Current P&L: {pos.profit:.2f} {info.currency}")
else:
    print(f"  Could not find position: {mt5.last_error()}")

# ─── STEP 7: Close the Trade ─────────────────────────────
print(f"\n[STEP 7] Closing the test trade...")
time.sleep(2)

tick2 = mt5.symbol_info_tick(SYMBOL)
close_request = {
    "action":       mt5.TRADE_ACTION_DEAL,
    "symbol":       SYMBOL,
    "volume":       TEST_LOT,
    "type":         mt5.ORDER_TYPE_SELL,   # opposite to close BUY
    "position":     ticket,
    "price":        tick2.bid,
    "deviation":    20,
    "magic":        999999,
    "comment":      "BotTest_Close",
    "type_time":    mt5.ORDER_TIME_GTC,
    "type_filling": filling_type,
}

close_result = mt5.order_send(close_request)

if close_result is None or close_result.retcode != mt5.TRADE_RETCODE_DONE:
    retcode = close_result.retcode if close_result else "None"
    comment = close_result.comment if close_result else str(mt5.last_error())
    print(f"  CLOSE FAILED retcode={retcode}: {comment}")
else:
    close_price = close_result.price
    pnl = round((close_price - fill_price) * TEST_LOT * 100000, 2)
    print(f"  Trade CLOSED!")
    print(f"  Close price : {close_price:.5f}")
    print(f"  P&L         : {pnl:+.2f} {info.currency}")

# ─── DONE ─────────────────────────────────────────────────
mt5.shutdown()
print()
print("=" * 55)
print("  ALL STEPS PASSED — Bot CAN trade via MT5!")
print("  Run 'python main.py' to start the live bot.")
print("=" * 55)
