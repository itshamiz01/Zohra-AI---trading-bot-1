"""
Telegram Command Interface
Your "chat" with the trading bot.
"""

import requests
import json
from datetime import datetime
from typing import Optional
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, STATE
from database import db
from data_feed import data_feed
from risk_manager import risk_manager

class TelegramInterface:
    """
    Command-based interface for monitoring and controlling the bot.
    Not a conversational AI — structured commands for reliability.
    """

    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.last_update_id = 0

    def send_message(self, text: str, chat_id: Optional[str] = None):
        """Send message to Telegram"""
        if not TELEGRAM_BOT_TOKEN:
            print(f"[TELEGRAM] {text}")
            return

        target = chat_id or TELEGRAM_CHAT_ID
        if not target:
            return

        # Split long messages
        max_len = 4000
        for i in range(0, len(text), max_len):
            chunk = text[i:i+max_len]
            try:
                requests.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": target, "text": chunk, "parse_mode": "HTML"},
                    timeout=10
                )
            except Exception as e:
                print(f"Telegram send failed: {e}")

    def send_trade_alert(self, symbol: str, direction: str, entry: float, 
                        stop: float, target: float, size: int):
        """Alert for new trade"""
        emoji = "🟢" if direction == "LONG" else "🔴"
        text = (
            f"{emoji} <b>NEW TRADE</b>\n"
            f"Symbol: {symbol}\n"
            f"Direction: {direction}\n"
            f"Entry: {entry:.5f}\n"
            f"Stop: {stop:.5f}\n"
            f"Target: {target:.5f}\n"
            f"Size: {size:,} units"
        )
        self.send_message(text)

    def send_exit_alert(self, symbol: str, pnl: float, reason: str):
        """Alert for closed trade"""
        emoji = "✅" if pnl > 0 else "❌"
        text = (
            f"{emoji} <b>TRADE CLOSED</b>\n"
            f"Symbol: {symbol}\n"
            f"P&L: ${pnl:.2f}\n"
            f"Reason: {reason}"
        )
        self.send_message(text)

    def send_daily_summary(self):
        """Send end-of-day P&L summary"""
        stats = db.get_performance_stats()
        text = (
            f"📊 <b>DAILY SUMMARY</b>\n"
            f"Daily P&L: ${STATE.daily_pnl:.2f}\n"
            f"Monthly P&L: ${STATE.monthly_pnl:.2f}\n"
            f"Total Trades: {stats['total_trades']}\n"
            f"Win Rate: {stats['win_rate']:.1f}%\n"
            f"Total P&L: ${stats['total_pnl']:.2f}"
        )
        self.send_message(text)

    def process_command(self, text: str) -> str:
        """
        Process incoming command and return response.
        """
        text = text.strip().lower()
        parts = text.split()
        command = parts[0] if parts else ""

        # ─── STATUS ───
        if command == "/status":
            account = data_feed.get_account_summary()
            positions = data_feed.get_open_positions()
            risk = risk_manager.get_status()

            msg = (
                f"📊 <b>ACCOUNT STATUS</b>\n"
                f"Balance: ${account.get('balance', 0):.2f}\n"
                f"Equity: ${account.get('equity', 0):.2f}\n"
                f"Open Positions: {len(positions)}\n"
                f"Trading: {'✅ ON' if risk['trading_enabled'] else '⛔ OFF'}\n"
                f"Daily P&L: ${risk['daily_pnl']:.2f}\n"
                f"Monthly P&L: ${risk['monthly_pnl']:.2f}"
            )

            if positions:
                msg += "\n\n<b>OPEN POSITIONS:</b>"
                for pos in positions:
                    msg += (f"\n{pos['symbol']} {pos['direction']} "
                           f"| P&L: ${pos['unrealized_pnl']:.2f}")

            return msg

        # ─── HISTORY ───
        elif command == "/history":
            limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
            trades = db.get_trade_history(limit)

            if not trades:
                return "📭 No trade history yet."

            msg = f"📜 <b>LAST {len(trades)} TRADES:</b>\n"
            for t in trades:
                emoji = "✅" if t['pnl_usd'] > 0 else "❌"
                msg += (f"\n{emoji} {t['symbol']} {t['direction']}"
                       f" | P&L: ${t['pnl_usd']:.2f}"
                       f" | {t['exit_reason']}")

            return msg

        # ─── EQUITY ───
        elif command == "/equity":
            curve = db.get_equity_curve(days=30)
            if not curve:
                return "📈 No equity data yet. Start trading first."

            latest = curve[-1]
            start = curve[0]
            change = ((latest['equity'] - start['equity']) / start['equity'] * 100) if start['equity'] > 0 else 0

            stats = db.get_performance_stats()

            return (
                f"📈 <b>EQUITY CURVE (30 days)</b>\n"
                f"Start: ${start['equity']:.2f}\n"
                f"Current: ${latest['equity']:.2f}\n"
                f"Change: {change:+.2f}%\n"
                f"Max Drawdown: {stats['max_drawdown_pct']:.1f}%"
            )

        # ─── STATS ───
        elif command == "/stats":
            stats = db.get_performance_stats()
            return (
                f"📊 <b>PERFORMANCE STATS</b>\n"
                f"Total Trades: {stats['total_trades']}\n"
                f"Win Rate: {stats['win_rate']:.1f}%\n"
                f"Avg P&L: ${stats['avg_pnl']:.2f}\n"
                f"Avg Win: ${stats['avg_win']:.2f}\n"
                f"Avg Loss: ${stats['avg_loss']:.2f}\n"
                f"Total P&L: ${stats['total_pnl']:.2f}\n"
                f"Max Drawdown: {stats['max_drawdown_pct']:.1f}%\n"
                f"Profit Factor: {stats['profit_factor']:.2f}"
            )

        # ─── WHY ───
        elif command == "/why":
            if len(parts) < 2:
                return "Usage: /why EURUSD\nShows last signal reason for a pair."

            symbol = parts[1].upper()
            # Get last signal from DB
            cursor = db.conn.cursor()
            cursor.execute(
                "SELECT * FROM signals WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
                (symbol,)
            )
            row = cursor.fetchone()

            if not row:
                return f"❓ No recent signals for {symbol}."

            columns = [desc[0] for desc in cursor.description]
            signal = dict(zip(columns, row))

            return (
                f"🧠 <b>LAST SIGNAL: {symbol}</b>\n"
                f"Time: {signal['timestamp']}\n"
                f"Signal: {signal['signal']}\n"
                f"Price: {signal['price']:.5f}\n"
                f"EMA Fast: {signal['ema_fast']:.5f}\n"
                f"EMA Slow: {signal['ema_slow']:.5f}\n"
                f"ATR: {signal['atr']:.5f}\n"
                f"Executed: {'Yes' if signal['executed'] else 'No'}"
            )

        # ─── PAUSE / RESUME ───
        elif command == "/pause":
            STATE.trading_enabled = False
            db.log_system("INFO", "Trading paused by user")
            return "⛔ <b>TRADING PAUSED</b>\nNo new positions will be opened. Existing positions remain active."

        elif command == "/resume":
            STATE.trading_enabled = True
            db.log_system("INFO", "Trading resumed by user")
            return "✅ <b>TRADING RESUMED</b>"

        # ─── HELP ───
        elif command == "/help":
            return (
                "🤖 <b>TRADING BOT COMMANDS</b>\n\n"
                "/status - Account balance, equity, open positions\n"
                "/history [n] - Last n trades (default 10)\n"
                "/equity - Equity curve summary\n"
                "/stats - Full performance statistics\n"
                "/why [SYMBOL] - Last signal reason (e.g., /why EURUSD)\n"
                "/pause - Stop opening new trades\n"
                "/resume - Resume trading\n"
                "/help - This message\n\n"
                "⏰ Bot checks for signals every hour."
            )

        else:
            return "❓ Unknown command. Type /help for available commands."

    def check_messages(self):
        """Poll for new Telegram messages (run in separate thread)"""
        if not TELEGRAM_BOT_TOKEN:
            return

        try:
            response = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self.last_update_id + 1},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                for update in data.get("result", []):
                    self.last_update_id = update["update_id"]

                    if "message" in update and "text" in update["message"]:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"]["text"]

                        response_text = self.process_command(text)
                        self.send_message(response_text, str(chat_id))

        except Exception as e:
            db.log_system("ERROR", f"Telegram poll failed: {e}")

# Singleton instance
telegram = TelegramInterface()
