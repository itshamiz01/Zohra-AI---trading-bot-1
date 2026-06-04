#!/usr/bin/env python3
"""
Trading Bot Entry Point
EMA + ATR Strategy on 1H Forex Charts
Paper Trading via MetaTrader 5 Demo Account

Setup:
1. Download MetaTrader 5: https://www.metatrader5.com/en/download
2. Open MT5 → File → Open an Account → pick any broker → Demo Account
3. Note your login number, password, and server name
4. Fill in .env (copy from .env.example) with those credentials
5. Keep MT5 running in background
6. Install dependencies: pip install -r requirements.txt
7. Run: python main.py

Environment Variables (put in .env file):
    MT5_LOGIN=12345678
    MT5_PASSWORD=your_demo_password
    MT5_SERVER=ICMarkets-Demo

Optional:
    TELEGRAM_BOT_TOKEN=your_bot_token
    TELEGRAM_CHAT_ID=your_chat_id
    GROQ_API_KEY=your_groq_key
"""

import os
import sys
import signal
from pathlib import Path

# Auto-load .env file if present
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded credentials from .env")
    else:
        load_dotenv()
except ImportError:
    pass

# Validate required env vars
required = ["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"]
missing  = [v for v in required if not os.getenv(v)]

if missing:
    print("❌ Missing required environment variables:")
    for v in missing:
        print(f"   - {v}")
    print("\nFill in your .env file (copy .env.example and edit it):")
    print("   MT5_LOGIN=12345678")
    print("   MT5_PASSWORD=your_demo_password")
    print("   MT5_SERVER=ICMarkets-Demo")
    print("\nGet these from MetaTrader 5: File → Open an Account → Demo")
    sys.exit(1)

# Import after env vars are loaded
from data_feed import data_feed
from scheduler import scheduler


def signal_handler(sig, frame):
    print("\n🛑 Shutting down gracefully...")
    scheduler.stop()
    data_feed.disconnect()
    sys.exit(0)


signal.signal(signal.SIGINT,  signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    print("=" * 60)
    print("   FOREX TRADING BOT — MetaTrader 5")
    print("   Strategy: EMA Crossover + ATR Filter")
    print("   Timeframe: 1H")
    print("   Mode: PAPER TRADING (Demo Account)")
    print("=" * 60)
    print()
    print("Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD")
    print("Risk: 1% per trade | Max 3 positions")
    print("Stop: 1.5x ATR | Target: 3x ATR")
    print()
    print("Telegram commands: /status /history /equity /stats /why /pause /resume /help")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)

    # ── Connect to MT5 first ──────────────────────────────────────────
    print("\n🔌 Connecting to MetaTrader 5...")
    if not data_feed.connect():
        print("\n❌ Could not connect to MetaTrader 5.")
        print("   Make sure MT5 is installed, open, and logged in to your demo account.")
        sys.exit(1)

    print()

    # ── Start the trading loop ────────────────────────────────────────
    try:
        scheduler.start()
    finally:
        data_feed.disconnect()
