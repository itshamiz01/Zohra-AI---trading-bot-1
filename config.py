"""
Trading Bot Configuration
All settings centralized. NEVER hardcode elsewhere.
"""

import os
from dataclasses import dataclass
from typing import List

# ─── METATRADER 5 ───
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))       # Your MT5 account number
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")          # MT5 account password
MT5_SERVER   = os.getenv("MT5_SERVER", "")            # e.g. "ICMarkets-Demo"

# ─── TELEGRAM ───
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── TRADING PARAMETERS ───
TIMEFRAME = "H1"   # 1 hour  (mapped to mt5.TIMEFRAME_H1 in data_feed)

# MT5 uses symbols WITHOUT underscore: EURUSD, GBPUSD, etc.
PAIRS: List[str] = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]

# Strategy: Dual EMA + ATR
EMA_FAST   = 20
EMA_SLOW   = 50
ATR_PERIOD = 14
ATR_MINIMUM = 0.0005   # Minimum ATR to trade (filters dead markets)

# Risk Management
RISK_PER_TRADE_PCT   = 0.01    # 1% of equity
MAX_OPEN_POSITIONS   = 3
MAX_DAILY_LOSS_PCT   = 0.03    # Stop trading if down 3%
MAX_MONTHLY_LOSS_PCT = 0.10    # Stop trading if down 10%
STOP_LOSS_ATR_MULT   = 1.5
TAKE_PROFIT_ATR_MULT = 3.0     # 2:1 R/R minimum
TRAILING_ACTIVATION_ATR = 1.0  # Move to BE at +1x ATR
TRAILING_STOP_ATR    = 1.5
MAX_HOLD_HOURS       = 120     # 5 days time stop

# Position sizing — MT5 uses LOTS (1 lot = 100,000 units)
MIN_LOT_SIZE = 0.01            # Micro lot
MAX_LOT_SIZE = 0.50            # 50K units = 0.5 lots
LOT_STEP     = 0.01            # Minimum lot increment

# ─── FREE LLM (Groq) ───
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL     = "llama-3.1-8b-instant"  # Free tier (llama3-8b-8192 was decommissioned)
GROQ_MAX_TOKENS = 500

# ─── SYSTEM ───
DB_PATH                 = "logs/trades.db"
LOG_LEVEL               = "INFO"
CHECK_INTERVAL_SECONDS  = 300   # 5 min between checks

@dataclass
class TradingState:
    """Runtime mutable state"""
    daily_pnl:       float = 0.0
    monthly_pnl:     float = 0.0
    trades_today:    int   = 0
    trading_enabled: bool  = True
    last_trade_time: str   = ""

STATE = TradingState()
