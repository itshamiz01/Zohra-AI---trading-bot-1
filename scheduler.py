"""
Main Trading Loop
Runs every hour to check signals, manage positions, log state.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict
from config import PAIRS, CHECK_INTERVAL_SECONDS, STATE
from database import db
from data_feed import data_feed
from strategy import strategy
from risk_manager import risk_manager
from executor import executor
from telegram_bot import telegram

class TradingScheduler:
    """
    Orchestrates the entire trading workflow.
    """

    def __init__(self):
        self.running = False
        self.last_hour_check = None
        self.telegram_thread = None

    def run_cycle(self):
        """
        One complete trading cycle:
        1. Get account state
        2. Check existing positions for exits
        3. Check for new signals
        4. Execute valid trades
        5. Log everything
        """
        now = datetime.utcnow()
        db.log_system("INFO", f"=== Cycle started at {now.isoformat()} ===")

        # ─── 1. Account State ───
        account = data_feed.get_account_summary()
        if not account:
            db.log_system("ERROR", "Failed to fetch account summary")
            return

        equity = account["equity"]
        balance = account["balance"]

        # ─── 2. Check Open Positions ───
        open_positions = data_feed.get_open_positions()
        db_positions = db.get_open_trades()

        # Check each open position for exit conditions
        for db_pos in db_positions:
            symbol = db_pos["symbol"]

            # Fetch recent candles
            df = data_feed.get_candles(symbol, count=50)
            if df.empty:
                continue

            exit_info = strategy.check_exit(df, db_pos)

            if exit_info:
                if exit_info["reason"] == "TRAIL_UPDATE":
                    # Update stop loss
                    executor.modify_stop(
                        db_pos["oanda_trade_id"],
                        exit_info["new_stop"]
                    )
                    db.log_system("INFO", 
                        f"Updated stop for {symbol} to {exit_info['new_stop']:.5f}")

                else:
                    # Close position
                    result = executor.close_position(
                        db_pos["trade_id"],
                        db_pos["oanda_trade_id"],
                        symbol,
                        db_pos["direction"]
                    )

                    if result.get("success"):
                        pnl = result["pnl_usd"]
                        risk_manager.update_pnl_state(pnl)

                        telegram.send_exit_alert(symbol, pnl, exit_info["reason"])
                        db.log_system("INFO", 
                            f"Closed {symbol}: ${pnl:.2f} ({exit_info['reason']})")

        # ─── 3. Check for New Signals ───
        # Only if we can trade
        allowed, reason = risk_manager.can_trade(equity, "", open_positions)

        if not allowed:
            db.log_system("INFO", f"Skipping new signals: {reason}")
        else:
            for symbol in PAIRS:
                # Skip if already in this pair
                if any(p["symbol"] == symbol for p in open_positions):
                    continue

                # Fetch data
                df = data_feed.get_candles(symbol, count=100)
                if df.empty or len(df) < 60:
                    continue

                # Generate signal
                signal = strategy.generate_signal(df)

                if signal:
                    signal["symbol"] = symbol

                    # Log signal
                    db.log_signal(symbol, signal["direction"], signal["entry"],
                                 signal["ema_fast"], signal["ema_slow"], signal["atr"])

                    # Validate with risk manager
                    validated = risk_manager.validate_signal(signal, equity, open_positions)

                    if validated:
                        # Execute
                        result = executor.open_position(validated)

                        if result.get("success"):
                            telegram.send_trade_alert(
                                symbol, signal["direction"],
                                result["fill_price"], signal["stop"],
                                signal["target"], validated["position_size"]
                            )

                            STATE.trades_today += 1
                            open_positions.append({
                                "symbol": symbol,
                                "direction": signal["direction"]
                            })

                            db.log_system("INFO", 
                                f"Opened {signal['direction']} {symbol}")

        # ─── 4. Log Equity ───
        open_pnl = sum(p.get("unrealized_pnl", 0) for p in open_positions)
        db.log_equity(equity, open_pnl, STATE.daily_pnl, STATE.monthly_pnl)

        # ─── 5. Daily Reset Check ───
        if self._should_reset_daily():
            risk_manager.reset_daily()
            telegram.send_daily_summary()
            db.log_system("INFO", "Daily stats reset")

        db.log_system("INFO", f"=== Cycle complete ===\n")

    def _should_reset_daily(self) -> bool:
        """Check if we should reset daily stats (new trading day)"""
        now = datetime.utcnow()
        # Forex day starts at 5pm EST (21:00 UTC)
        # Reset if we're past 21:00 UTC and haven't reset today
        if now.hour == 21 and now.minute < 5:
            return True
        return False

    def _telegram_polling(self):
        """Background thread for Telegram commands"""
        while self.running:
            try:
                telegram.check_messages()
            except Exception as e:
                db.log_system("ERROR", f"Telegram polling error: {e}")
            time.sleep(5)  # Check every 5 seconds

    def start(self):
        """Start the trading loop"""
        self.running = True

        db.log_system("INFO", "🚀 Trading bot started")
        telegram.send_message("🚀 <b>Trading Bot Started</b>\n1H EMA+ATR Strategy\nPaper Trading Mode")

        # Start Telegram polling in background
        self.telegram_thread = threading.Thread(target=self._telegram_polling)
        self.telegram_thread.daemon = True
        self.telegram_thread.start()

        # Main loop
        while self.running:
            now = datetime.utcnow()

            # Run at the start of each hour
            if self.last_hour_check is None or now.hour != self.last_hour_check.hour:
                try:
                    self.run_cycle()
                    self.last_hour_check = now
                except Exception as e:
                    error_msg = f"Cycle error: {str(e)}"
                    db.log_system("ERROR", error_msg)
                    telegram.send_message(f"⚠️ <b>Error:</b> {error_msg}")

            # Sleep until next check
            time.sleep(CHECK_INTERVAL_SECONDS)

    def stop(self):
        """Graceful shutdown"""
        self.running = False
        db.log_system("INFO", "Trading bot stopped")
        telegram.send_message("🛑 <b>Trading Bot Stopped</b>")

# Singleton instance
scheduler = TradingScheduler()
