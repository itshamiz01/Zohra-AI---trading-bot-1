"""
Trading Bot Configuration — MetaTrader 5
All settings centralized. NEVER hardcode elsewhere.
"""

import os
from dataclasses import dataclass
from typing import List

# ─── METATRADER 5 ───────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")    # e.g. "ICMarkets-Demo"

# ─── TELEGRAM ───────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── TRADING PARAMETERS ─────────────────────────
TIMEFRAME = "H1"

# MT5 symbol names — no underscores
PAIRS: List[str] = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]

# Strategy: Dual EMA + ATR
EMA_FAST   = 20
EMA_SLOW   = 50
ATR_PERIOD = 14
ATR_MINIMUM = 0.0005    # Minimum ATR to trade (filters dead markets)

# Risk Management
RISK_PER_TRADE_PCT    = 0.005       # 0.5% of equity per trade
MAX_OPEN_POSITIONS    = 3
MAX_DAILY_LOSS_PCT    = 0.02        # Kill switch: stop if down 2%
MAX_MONTHLY_LOSS_PCT  = 0.10        # Stop trading if down 10%
STOP_LOSS_ATR_MULT    = 1.5
TAKE_PROFIT_ATR_MULT  = 3.0         # 2:1 R/R minimum
TRAILING_ACTIVATION_ATR = 1.0       # Move to BE at +1× ATR
TRAILING_STOP_ATR     = 1.5
MAX_HOLD_HOURS        = 120          # 5 days time stop

# Position sizing — lots (MT5 standard)
MIN_LOT_SIZE = 0.01
MAX_LOT_SIZE = 2.0
LOT_STEP     = 0.01

# ─── FREE LLM (Groq) ────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = "llama3-8b-8192"
GROQ_MAX_TOKENS = 500

# ─── SYSTEM ─────────────────────────────────────
DB_PATH                = "logs/trades.db"
LOG_LEVEL              = "INFO"
CHECK_INTERVAL_SECONDS = 300          # 5 min between checks
MAGIC_NUMBER           = 20260604     # MT5 trade identifier

@dataclass
class TradingState:
    """Runtime mutable state"""
    daily_pnl:       float = 0.0
    monthly_pnl:     float = 0.0
    trades_today:    int   = 0
    trading_enabled: bool  = True
    last_trade_time: str   = ""

STATE = TradingState()
