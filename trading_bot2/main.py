#!/usr/bin/env python3
"""
Trading Bot Entry Point
EMA + ATR Strategy on 1H Forex Charts
MetaTrader 5

Setup:
1. Install MetaTrader 5 terminal from your broker
2. Enable "Allow Algo Trading" in MT5
3. Create Telegram bot via @BotFather, get token
4. Set environment variables (see below)
5. Install dependencies: pip install MetaTrader5 pandas
6. Run: python main.py

Environment Variables:
    set MT5_LOGIN=your_account_number
    set MT5_PASSWORD=your_password
    set MT5_SERVER=YourBroker-Demo
    set TELEGRAM_BOT_TOKEN=your_bot_token
    set TELEGRAM_CHAT_ID=your_chat_id
    set GROQ_API_KEY=your_groq_key     # Optional, for LLM Q&A
"""

import os
import sys
import signal

# Validate required env vars
required = ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"]
missing  = [v for v in required if not os.getenv(v)]

if missing:
    print("❌ Missing required environment variables:")
    for v in missing:
        print(f"   - {v}")
    print("\nSet them before running:")
    print("   set MT5_LOGIN=123456789")
    print("   set MT5_PASSWORD=your_password")
    print("   set MT5_SERVER=ICMarkets-Demo")
    print("\nOptional (for Telegram alerts):")
    print("   set TELEGRAM_BOT_TOKEN=xxx")
    print("   set TELEGRAM_CHAT_ID=xxx")
    sys.exit(1)

from scheduler import scheduler

def signal_handler(sig, frame):
    print("\n🛑 Shutting down gracefully...")
    scheduler.stop()
    sys.exit(0)

signal.signal(signal.SIGINT,  signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    print("=" * 60)
    print("   ZOHRA TRADING BOT")
    print("   Strategy: EMA Crossover + ATR Filter")
    print("   Timeframe: 1H | Broker: MetaTrader 5")
    print("=" * 60)
    print()
    print("Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD")
    print("Risk: 0.5% per trade | Max 3 positions")
    print("Stop: 1.5×ATR | Target: 3×ATR")
    print()
    print("Telegram commands: /status /history /equity /stats /why /pause /resume /help")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)

    scheduler.start()
