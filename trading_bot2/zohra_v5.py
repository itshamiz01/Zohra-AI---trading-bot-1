"""
Zohra v5 Integration Script
============================
Replaces your existing zohra_v4.py with enhanced features.

WHAT CHANGED:
- Score threshold: 95/100 (was 79)
- Position size: 0.5% risk, max 2 lots (was 1%, unlimited)
- Kill switch: -2% daily loss = STOP
- Auto-manager: Built in, no separate script needed
- Reject logger: Every blocked trade saved with reason
- Trade quality: A+/A/B with different management
- Partial TP: 50% at 1R, 50% trails

USAGE:
    python zohra_v5.py

NO MANUAL OVERRIDE FUNCTIONS.
If you want to force a trade, use a different bot.
This one protects capital first.
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time
import json

from zohra_enhanced_core import zohra_v5, TradeQuality, MarketRegime

# ─── CONFIG ───
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"]
TIMEFRAME = mt5.TIMEFRAME_H1
STARTING_EQUITY = None  # Will be set on first run


def get_data(symbol: str, bars: int = 200) -> pd.DataFrame:
    """Fetch OHLCV from MT5"""
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, bars)
    if rates is None:
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df


def get_equity() -> float:
    """Get current account equity"""
    account = mt5.account_info()
    return account.equity if account else 0.0


def place_trade(trade: dict):
    """Execute trade via MT5"""
    symbol = trade["symbol"]
    direction = trade["direction"]
    lots = trade["lots"]
    entry = trade["entry_price"]
    stop = trade["stop_loss"]
    tp = trade["take_profit"]

    # Select symbol
    if not mt5.symbol_select(symbol, True):
        print(f"❌ Cannot select {symbol}")
        return None

    # Determine order type
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None

    price = tick.ask if direction == "LONG" else tick.bid

    order_type = mt5.ORDER_TYPE_BUY if direction == "LONG" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "price": price,
        "sl": stop,
        "tp": tp,
        "deviation": 10,
        "magic": 234000,
        "comment": f"ZOHRAv5_{trade['quality']}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ TRADE EXECUTED: {symbol} {direction} {lots} lots @ {price}")
        print(f"   SL: {stop} | TP: {tp} | Quality: {trade['quality']} | Score: {trade['score']}")

        # Store active trade
        trade["ticket"] = result.order
        trade["open_time"] = datetime.utcnow()
        zohra_v5.active_trades[symbol] = trade

        return result.order
    else:
        print(f"❌ Order failed: {result.retcode} - {result.comment}")
        return None


def manage_trades():
    """Check and manage all open trades"""
    positions = mt5.positions_get()

    if positions is None:
        return

    for pos in positions:
        symbol = pos.symbol

        if symbol not in zohra_v5.active_trades:
            continue

        trade = zohra_v5.active_trades[symbol]

        # Get current data
        df = get_data(symbol, 50)
        if df.empty:
            continue

        # Check management rules
        action = zohra_v5.manage_open_trade(trade, df)

        if action == "CLOSE_FULL":
            close_position(pos, symbol, "Manager exit")
            del zohra_v5.active_trades[symbol]

        elif action == "CLOSE_HALF":
            # MT5 partial close
            close_volume = pos.volume / 2
            close_partial(pos, symbol, close_volume, "TP1 - Half close")
            trade["half_closed"] = True

            # Move SL to BE on remaining
            new_sl = trade["entry_price"]
            modify_position(pos, new_sl, pos.tp)
            trade["be_moved"] = True

        elif action == "MOVE_BE":
            new_sl = trade["entry_price"]
            modify_position(pos, new_sl, pos.tp)
            trade["be_moved"] = True
            print(f"🔄 {symbol}: SL moved to breakeven")

        elif action == "TRAIL":
            # Trail behind recent structure
            atr = zohra_v5._calculate_atr(df, 14).iloc[-1]

            if trade["direction"] == "LONG":
                new_sl = df.iloc[-1]["close"] - (atr * 1.5)
                if new_sl > pos.sl:
                    modify_position(pos, new_sl, pos.tp)
            else:
                new_sl = df.iloc[-1]["close"] + (atr * 1.5)
                if new_sl < pos.sl:
                    modify_position(pos, new_sl, pos.tp)


def close_position(pos, symbol: str, reason: str):
    """Close full position"""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    price = tick.bid if pos.type == 0 else tick.ask  # 0 = BUY, 1 = SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
        "position": pos.ticket,
        "price": price,
        "deviation": 10,
        "magic": 234000,
        "comment": f"Close_{reason}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        pnl = pos.profit
        emoji = "✅" if pnl > 0 else "❌"
        print(f"{emoji} CLOSED {symbol}: ${pnl:.2f} ({reason})")

        # Update stats
        zohra_v5.session_stats["total_trades"] += 1
        if pnl > 0:
            zohra_v5.session_stats["win_count"] += 1
        else:
            zohra_v5.session_stats["loss_count"] += 1
        zohra_v5.session_stats["total_pnl"] += pnl


def close_partial(pos, symbol: str, volume: float, reason: str):
    """Close partial position"""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    price = tick.bid if pos.type == 0 else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": round(volume, 2),
        "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
        "position": pos.ticket,
        "price": price,
        "deviation": 10,
        "magic": 234000,
        "comment": f"Partial_{reason}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✂️ PARTIAL CLOSE {symbol}: {volume} lots ({reason})")


def modify_position(pos, new_sl: float, new_tp: float):
    """Modify SL/TP"""
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": pos.ticket,
        "sl": round(new_sl, 5),
        "tp": round(new_tp, 5),
    }

    mt5.order_send(request)


def print_status():
    """Print current status"""
    equity = get_equity()

    print("\n" + "=" * 60)
    print(f"ZOHRA v5 — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 60)
    print(f"Equity: ${equity:.2f}")
    print(f"Daily trades: {zohra_v5.daily_trades}/{MAX_DAILY_TRADES}")
    print(f"Kill switch: {'🔴 ACTIVE' if zohra_v5.kill_switch else '🟢 OFF'}")
    print(f"Active trades: {len(zohra_v5.active_trades)}")

    if zohra_v5.active_trades:
        for sym, trade in zohra_v5.active_trades.items():
            print(f"  {sym}: {trade['direction']} | Q:{trade['quality']} | S:{trade['score']}")

    # Rejection analysis
    analysis = zohra_v5.get_rejection_analysis()
    if "total_rejected" in analysis:
        print(f"\nRejections today: {analysis['total_rejected']}")
        print(f"Worst filter: {analysis.get('worst_regime', 'N/A')}")

    print("=" * 60)


def main():
    """Main loop"""
    global STARTING_EQUITY

    # Initialize MT5
    if not mt5.initialize():
        print("❌ MT5 init failed")
        return

    print("🚀 ZOHRA v5 Enhanced Engine Started")
    print("   Score threshold: 95/100")
    print("   Risk per trade: 0.5%")
    print("   Max lots: 2.0")
    print("   Kill switch: -2% daily")
    print("   NO MANUAL OVERRIDE")
    print()

    # Set starting equity
    STARTING_EQUITY = get_equity()
    zohra_v5.reset_daily()

    cycle = 0

    try:
        while True:
            cycle += 1
            now = datetime.utcnow()

            # Reset at midnight UTC
            if now.hour == 0 and now.minute < 5:
                zohra_v5.reset_daily()
                STARTING_EQUITY = get_equity()
                print("🌅 New day — counters reset")

            # Print status every cycle
            if cycle % 6 == 0:  # Every ~30 minutes
                print_status()

            # Manage existing trades first
            manage_trades()

            # Scan for new trades
            equity = get_equity()

            for symbol in SYMBOLS:
                # Skip if already in this symbol
                if symbol in zohra_v5.active_trades:
                    continue

                df = get_data(symbol, 200)
                if df.empty:
                    continue

                result = zohra_v5.scan_and_trade(symbol, df, equity, STARTING_EQUITY)

                if result["rejected"]:
                    if cycle % 6 == 0:  # Only print rejections periodically
                        print(f"⛔ {symbol}: {result['reason']}")
                else:
                    trade = result["trade"]
                    place_trade(trade)

            # Sleep 5 minutes
            time.sleep(300)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")

        # Save stats
        with open("zohra_stats.json", "w") as f:
            json.dump(zohra_v5.session_stats, f, indent=2)

        # Save rejections
        zohra_v5._save_rejections()

        print("Stats saved. Goodbye.")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
