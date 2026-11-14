"""
╔══════════════════════════════════════════════════════╗
║          ZOHRA TRADING ENGINE — SETTINGS            ║
║     MetaTrader 5 Only — Production Configuration    ║
╚══════════════════════════════════════════════════════╝

All configuration centralized here.
Never hardcode values elsewhere.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from dataclasses import dataclass, field
from typing import List, Dict, Optional

# ════════════════════════════════════════════════
#  METATRADER 5 CONNECTION (Legacy single-account — backward compatible)
# ════════════════════════════════════════════════
MT5_LOGIN    = int(os.getenv("MT5_LOGIN") or "0")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")           # e.g. "ICMarkets-Demo"

# ════════════════════════════════════════════════
#  MULTI-ACCOUNT CONFIGURATION
# ════════════════════════════════════════════════
@dataclass
class AccountConfig:
    """Configuration for a single MT5 account."""
    account_id: str
    login: int
    password: str
    server: str
    terminal_path: str
    name: str = ""
    magic_offset: int = 0
    enabled: bool = True

def _load_account_configs() -> 'List[AccountConfig]':
    """Load multi-account configurations from environment variables."""
    accounts = []
    num_accounts = int(os.getenv("ZOHRA_ACTIVE_ACCOUNTS", "3"))
    for i in range(1, num_accounts + 1):
        login_str = os.getenv(f"MT5_ACCOUNT_{i}_LOGIN", "0")
        login = int(login_str) if login_str and login_str != "0" else 0
        password = os.getenv(f"MT5_ACCOUNT_{i}_PASSWORD", "")
        server = os.getenv(f"MT5_ACCOUNT_{i}_SERVER", "")
        terminal_path = os.getenv(f"MT5_ACCOUNT_{i}_TERMINAL_PATH", "")
        name = os.getenv(f"MT5_ACCOUNT_{i}_NAME", f"Account {i}")
        # Skip accounts with no login configured
        enabled = login > 0 and password not in ("", "CHANGE_ME")
        accounts.append(AccountConfig(
            account_id=f"account_{i:02d}",
            login=login,
            password=password,
            server=server,
            terminal_path=terminal_path.strip('"').strip("'"),
            name=name.strip('"').strip("'"),
            magic_offset=(i - 1) * 100,
            enabled=enabled,
        ))
    # Fallback: if no multi-account vars, create single account from legacy vars
    if not accounts or all(not a.enabled for a in accounts):
        if MT5_LOGIN:
            accounts = [AccountConfig(
                account_id="account_01",
                login=MT5_LOGIN,
                password=MT5_PASSWORD,
                server=MT5_SERVER,
                terminal_path=os.getenv("MT5_TERMINAL_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe").strip('"').strip("'"),
                name="Account 1 (Primary)",
                magic_offset=0,
                enabled=True,
            )]
    return accounts

ACCOUNT_CONFIGS: List[AccountConfig] = _load_account_configs()
ACTIVE_ACCOUNT_CONFIGS: List[AccountConfig] = [a for a in ACCOUNT_CONFIGS if a.enabled]

# ════════════════════════════════════════════════
#  DHAN CONNECTION
# ════════════════════════════════════════════════
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")
DHAN_CLIENT_ID    = os.getenv("DHAN_CLIENT_ID", "")

# ════════════════════════════════════════════════
#  COINDCX CONNECTION
# ════════════════════════════════════════════════
COINDCX_API_KEY    = os.getenv("COINDCX_API_KEY", "")
COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET", "")

# ════════════════════════════════════════════════
#  MULTI-BROKER CONTROLS
# ════════════════════════════════════════════════
ACTIVE_BROKERS = [b.strip() for b in os.getenv("ACTIVE_BROKERS", "mt5").lower().split(",") if b.strip()]
DEFAULT_BROKER = os.getenv("DEFAULT_BROKER", "mt5").lower().strip()

# Live trading is a Tier 4 action in the Zohra AI Bible. The default is paper
# mode, which blocks live broker order placement unless explicitly changed.
TRADING_EXECUTION_MODE = os.getenv("TRADING_EXECUTION_MODE", "paper").lower().strip()
LIVE_TRADING_PREAUTHORIZED = os.getenv("LIVE_TRADING_PREAUTHORIZED", "0").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
LIVE_TRADING_PREAUTH_TOKEN = os.getenv("LIVE_TRADING_PREAUTH_TOKEN", "")

import json

# MT5 symbol names — strictly restricted to Gold (XAUUSD)
def load_symbol_registry() -> List[Dict]:
    symbols_file = os.path.join(os.path.dirname(__file__), "symbols.json")
    fallback = [
        {"symbol": "XAUUSD", "sector": "Metals", "max_spread_pips": 5.0, "enabled": True, "contract_size": 100.0}
    ]
    if not os.path.exists(symbols_file):
        return fallback
    try:
        with open(symbols_file, "r") as f:
            data = json.load(f)
            return data.get("symbols", fallback)
    except Exception:
        return fallback

SYMBOL_REGISTRY = load_symbol_registry()

# Multi-Asset Universe Configuration
GOLD_SYMBOL: str = "XAUUSD"
ALLOWED_SYMBOLS: List[str] = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]
ALLOWED_METALS: List[str] = ["XAUUSD"]
FOREX_PAIRS: List[str] = ["GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]
GOLD_PAIRS: List[str] = ["XAUUSD"]
INDICES: List[str] = []
ACTIVE_PAIRS: List[str] = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]

for symbol in SYMBOL_REGISTRY:
    symbol["enabled"] = symbol.get("symbol") in ALLOWED_SYMBOLS

# Override active symbols from .env if set
_env_traded = os.getenv("TRADED_SYMBOLS", "")
if _env_traded:
    parsed_symbols = [s.strip().upper() for s in _env_traded.split(",") if s.strip()]
    if parsed_symbols:
        ACTIVE_PAIRS = parsed_symbols
        ALLOWED_SYMBOLS = list(dict.fromkeys(ALLOWED_SYMBOLS + parsed_symbols))
if not ACTIVE_PAIRS:
    ACTIVE_PAIRS = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]

# Diagnostic Mode Flag
TRADING_DIAGNOSTIC_MODE = os.getenv("TRADING_DIAGNOSTIC_MODE", "1").lower() in ("1", "true", "yes", "on")

# ════════════════════════════════════════════════
#  TIMEFRAMES
# ════════════════════════════════════════════════
# Primary timeframes for analysis
TF_DAILY  = "D1"
TF_H4     = "H4"
TF_H1     = "H1"
TF_M15    = "M15"
TF_M5     = "M5"

# ════════════════════════════════════════════════
#  RISK MANAGEMENT
# ════════════════════════════════════════════════
RISK_PER_TRADE_PCT    = 0.01      # 1.0% base risk per trade (scaled by grade multiplier)
ALLOW_C_SETUPS = True      # Allow speculative C-grade setups (25% position size)
HYBRID_SCALPER_MODE   = True      # Execute Layer 1 Scout Probe orders immediately and scale via Layer 2 Committee
MAX_OPEN_POSITIONS    = 5
MAX_SCALE_UP_TICKETS_PER_SYMBOL = 3  # Max tickets per symbol (original + scale-ups)
METAL_SYMBOLS = {"XAUUSD", "XAGUSD"}
METAL_LOT_MULTIPLIER = 0.5            # 50% reduced lot size for metals (higher volatility)

# ════════════════════════════════════════════════
#  CRYPTOCURRENCY ENGINE PARAMETERS
# ════════════════════════════════════════════════
CRYPTO_VOLATILITY_THRESHOLD = 0.04    # 4% standard volatility threshold
CRYPTO_MAX_SPREAD_PIPS      = 50.0    # 50.0 spread units limit (e.g. USDT)
CRYPTO_MAX_EXPOSURE_PCT     = 0.20    # Max 20% of account allocated to crypto
CRYPTO_PORTFOLIO_TARGET_ALLOCATIONS = {
    "BTCUSDT": 0.50,                  # Target 50% of crypto portfolio in BTC
    "ETHUSDT": 0.30,                  # Target 30% of crypto portfolio in ETH
    "CASH": 0.20                      # Target 20% in stablecoins / reserve cash
}
MAX_DAILY_LOSS_PCT    = 0.08      # Kill switch: stop if down 8% (~$16-$20 on small account)
MAX_WEEKLY_LOSS_PCT   = 0.15      # Halt week if down 15%
MAX_MONTHLY_LOSS_PCT  = 0.25      # Halt month if down 25%
MAX_DRAWDOWN_PCT      = 0.10      # Hard stop if equity drops 10% from session start
MAX_DAILY_TRADES = 50        # Max trades per day across all pairs
MAX_DAILY_TRADES_SCALP = 50       # Max scalp trades per day
MAX_SECTOR_POSITIONS = {
    "Forex": 3,
    "Metals": 2,
    "Indices": 5
}
MAX_CURRENCY_EXPOSURE = 5        # Max concurrent positions exposing metals (USD quote)

# Lot caps
MIN_LOT_SIZE = 0.01
MAX_LOT_SIZE = 2.0
LOT_STEP     = 0.01

# ════════════════════════════════════════════════
#  INTELLIGENCE LAYER PARAMETERS
# ════════════════════════════════════════════════
INTELLIGENCE_MTF_TIMEFRAMES = ["MN", "W1", "D1", "H4", "H1", "M30", "M15", "M5"]
INTELLIGENCE_MIN_TF_ALIGNMENT = 3            # Minimum aligned timeframes before trade approval
INTELLIGENCE_MACRO_LOOKAHEAD_HOURS = 4       # Hours ahead to check for macro events
INTELLIGENCE_REGIME_UPDATE_INTERVAL = 300    # Seconds between regime re-evaluation
INTELLIGENCE_PORTFOLIO_REBALANCE_THRESHOLD = 0.10  # 10% deviation before rebalance suggested
INTELLIGENCE_OPTIMIZER_MAX_ITERATIONS = 500  # Cap on optimizer grid/walk-forward iterations
INTELLIGENCE_SMC_MIN_CONFLUENCE = 3          # Minimum SMC confluence signals for high confidence
INTELLIGENCE_CROSS_MARKET_ASSETS = ["XAUUSD", "XAGUSD"]

# ════════════════════════════════════════════════
#  VALIDATION & MONITORING ECOSYSTEM
# ════════════════════════════════════════════════
VALIDATION_SLIPPAGE_PIPS = 0.5               # Default slippage simulated
VALIDATION_LATENCY_MS = 150.0                # Simulated broker latency
VALIDATION_COMMISSION_USD_PER_LOT = 3.50     # Virtual broker commission per lot (each side)
VALIDATION_HEALTH_POLL_INTERVAL = 15.0       # Poll broker connection status every 15s

# ════════════════════════════════════════════════
#  DYNAMIC TRADE CLASSIFICATION SYSTEM
# ════════════════════════════════════════════════
# Institutional-grade opportunity grading and capital allocation.
# Each setup is classified into a quality tier that dynamically
# controls position size, risk allocation, and execution priority.
#
#   Grade    Score    Action        Position%   Risk-R   Priority
#   ─────    ─────    ──────        ─────────   ──────   ────────
#   A+       90-100   EXECUTE       100%        1.00R    HIGHEST
#   A        80-89    EXECUTE        75%        0.75R    HIGH
#   B        70-79    EXECUTE        50%        0.50R    NORMAL
#   C        60-69    OPTIONAL       25%        0.25R    LOW
#   REJECT   <60      REJECT          0%        0.00R    NONE
#
TRADE_CLASSIFICATION = {
    "A+":     {"min_score": 90, "max_score": 100, "position_mult": 1.00, "risk_r": 1.00, "priority": "HIGHEST",
               "classification": "Elite Institutional Opportunity", "action": "EXECUTE"},
    "A":      {"min_score": 80, "max_score": 89,  "position_mult": 0.75, "risk_r": 0.75, "priority": "HIGH",
               "classification": "High Probability Opportunity", "action": "EXECUTE"},
    "B":      {"min_score": 70, "max_score": 79,  "position_mult": 0.50, "risk_r": 0.50, "priority": "NORMAL",
               "classification": "Good Opportunity", "action": "EXECUTE"},
    "C":      {"min_score": 60, "max_score": 69,  "position_mult": 0.25, "risk_r": 0.25, "priority": "LOW",
               "classification": "Speculative Opportunity", "action": "OPTIONAL"},
    "REJECT": {"min_score": 0,  "max_score": 59,  "position_mult": 0.00, "risk_r": 0.00, "priority": "NONE",
               "classification": "Low Quality — Rejected", "action": "REJECT"},
}

# ════════════════════════════════════════════════
#  DRAWDOWN ADAPTATION TABLE
# ════════════════════════════════════════════════
# Automatically reduces all position sizes as drawdown increases.
# Key = upper bound of drawdown %, Value = risk multiplier.
#
#   Drawdown       Risk Multiplier    Effect
#   ────────       ───────────────    ──────
#   0% – 2%       1.00 (100%)        Normal risk
#   2% – 4%       0.75 (75%)         Reduce by 25%
#   4% – 6%       0.50 (50%)         Reduce by 50%
#   6% – 8%       0.25 (25%)         Reduce by 75%
#   > 8%          0.00 (0%)          TRADING PAUSE
#
DRAWDOWN_RISK_SCALING = {
    2.0: 1.00,
    4.0: 0.75,
    6.0: 0.50,
    8.0: 0.25,
}
TRADING_PAUSE_DRAWDOWN_PCT = 8.0

# R:R requirements
MIN_RR_SWING = 1.5
MIN_RR_SCALP = 1.2

# ════════════════════════════════════════════════
#  SMC SIGNAL SCORING
# ════════════════════════════════════════════════
MIN_SMC_SCORE_SWING   = 65        # Minimum score to enter swing trade
MIN_SMC_SCORE_STRICT  = 95        # Strict mode (ZohraV5 enhanced mode)
FVG_MIN_SIZE_MULT     = 0.3       # FVG must be ≥ 0.3×ATR
OB_DISPLACEMENT_MULT  = 1.5       # Displacement ≥ 1.5×ATR
EQUAL_LEVEL_THRESH    = 0.3       # Equal H/L if within 0.3×ATR

# ════════════════════════════════════════════════
#  SCALPING ENGINE
# ════════════════════════════════════════════════
SCALP_TIMEFRAME      = "M5"
SCALP_PAIRS          = ["XAUUSD"]
SCALP_SESSION_START  = 13         # 13:00 UTC (London/NY overlap start)
SCALP_SESSION_END    = 17         # 17:00 UTC
MAX_SPREAD_PIPS      = 2.0        # Skip trade if spread > 2 pips
MIN_ADX_SCALP        = 25         # Minimum ADX for scalp
STRONG_ADX_SCALP     = 25         # Strong trend threshold
STALL_BARS           = 3          # Close if price stalls 3 bars

# EMA config for scalping
SCALP_EMA_FAST = 8
SCALP_EMA_SLOW = 21

# ════════════════════════════════════════════════
#  POSITION MANAGEMENT
# ════════════════════════════════════════════════
PARTIAL_CLOSE_R  = 1.0            # Close 50% at 1R
FULL_CLOSE_R     = 2.0            # Close remaining at 2R
BE_TRIGGER_R     = 0.5            # Move to breakeven at 0.5R profit
TRAIL_BEHIND_ATR = 1.5            # Trail SL by 1.5×ATR behind price

# ════════════════════════════════════════════════
#  SESSIONS (UTC hours)
# ════════════════════════════════════════════════
SESSIONS: Dict[str, tuple] = {
    "Asian":   (0, 8),
    "London":  (7, 16),
    "NewYork": (12, 21),
    "Overlap": (13, 17),
}
HIGH_PRIORITY_SESSIONS = ["Overlap", "London", "NewYork"]

# ════════════════════════════════════════════════
#  TECHNICAL INDICATORS
# ════════════════════════════════════════════════
EMA_FAST    = 20
EMA_SLOW    = 50
EMA_TREND   = 200
ATR_PERIOD  = 14
RSI_PERIOD  = 14
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9
BB_PERIOD   = 20
BB_STD      = 2
ADX_PERIOD  = 14

# ════════════════════════════════════════════════
#  DATABASE
# ════════════════════════════════════════════════
# Bot details & Specialization Profile
from zohra.config.bot_profile import load_bot_profile, BotSpecializationProfile

BOT_NAME = os.getenv("BOT_NAME", "Bot A")
BOT_ID   = os.getenv("BOT_ID", "ZOHRA_BOT_A")
BOT_ROLE = os.getenv("BOT_ROLE", os.getenv("BOT_ID", "BOT_1_TREND"))
BOT_PROFILE: BotSpecializationProfile = load_bot_profile(BOT_ROLE)

# SQLite (default / fallback)
DB_PATH = os.getenv("DB_PATH", "logs/zohra_trades_a.db")
CHROMA_PATH = os.getenv("CHROMA_PATH", "logs/chroma_db_a")

# PostgreSQL (preferred for production)
POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB       = os.getenv("POSTGRES_DB", "zohra_trading")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "zohra")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# Set USE_POSTGRES=1 in .env to switch to PostgreSQL
USE_POSTGRES = os.getenv("USE_POSTGRES", "0") == "1"

# ════════════════════════════════════════════════
#  NOTIFICATIONS (Telegram)
# ════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

#  AI / LLM INTEGRATION (Gemini API & local DBs)
# ════════════════════════════════════════════════
CHAT_PROVIDER   = os.getenv("CHAT_PROVIDER", "openrouter")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "")
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = 500
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
NETWORK_AVAILABLE = os.getenv("NETWORK_AVAILABLE", "1").lower() in ("1", "true", "yes", "on")

# ════════════════════════════════════════════════
#  REPORTING
# ════════════════════════════════════════════════
LOG_DIR           = os.getenv("ZOHRA_LOG_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs"))
REPORTS_DIR       = os.path.join(LOG_DIR, "reports")
JOURNAL_CSV       = os.getenv("JOURNAL_CSV", os.path.join(LOG_DIR, "zohra_journal_a.csv"))
JOURNAL_FILE      = os.getenv("JOURNAL_FILE", os.path.join(LOG_DIR, "decision_journal_a.jsonl"))
REJECTED_LOG      = os.getenv("REJECTED_LOG", os.path.join(LOG_DIR, "rejected_trades_a.json"))
WEIGHTS_FILE      = os.getenv("WEIGHTS_FILE", os.path.join(LOG_DIR, "strategy_weights_a.json"))
SYSTEM_LOG        = os.getenv("SYSTEM_LOG", os.path.join(LOG_DIR, "zohra_engine_a.log"))
BRAIN_LOG         = os.getenv("BRAIN_LOG", os.path.join(LOG_DIR, "zohra_brain_a.log"))

# Cross-bot correlation monitoring shared log directory
# All bot instances write signal snapshots here for correlation analysis
_raw_cross_dir = os.getenv("CROSS_BOT_LOG_DIR", os.path.join(LOG_DIR, "cross_bot"))
CROSS_BOT_LOG_DIR = os.path.normpath(_raw_cross_dir.strip('"\''))

# MT5 executable path for instance containment
MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

# ════════════════════════════════════════════════
#  ENGINE TIMING
# ════════════════════════════════════════════════
SCAN_INTERVAL_SEC   = 15         # Check for new candle every 15s
MANAGE_INTERVAL_SEC = 15         # Manage positions every 15s
REPORT_TIME_UTC     = "23:50"    # Generate daily report time
CHECK_INTERVAL_SECONDS = 300     # 5 min between standard checks

# ════════════════════════════════════════════════
#  MAGIC NUMBERS (MT5 trade identifiers)
#  Derived from BOT_ID to ensure each bot instance
#  uses unique MAGIC numbers for trade attribution.
# ════════════════════════════════════════════════
def _derive_magic_offset(bot_id: str) -> int:
    """Generates a small unique offset from BOT_ID for MAGIC number isolation."""
    # Map known bot suffixes to stable offsets; fallback to hash-based
    suffix = bot_id.strip().upper().split("_")[-1] if bot_id else "A"
    known = {"A": 0, "B": 100, "C": 200}
    return known.get(suffix, abs(hash(bot_id)) % 900 + 100)

_magic_offset = _derive_magic_offset(BOT_ID)
MAGIC_SMC     = 20260604 + _magic_offset   # SMC swing trades (unique per bot)
MAGIC_SCALP   = 20260605 + _magic_offset   # Scalping trades (unique per bot)

# Simulated small account capital override (set to None for real balance usage)
VIRTUAL_EQUITY_OVERRIDE = 150.0

# Daily take profit target. Bot halts when daily_pnl reaches this value ($50/day per account).
DAILY_PROFIT_TARGET = float(os.getenv("DAILY_PROFIT_TARGET", "50.0"))

# ════════════════════════════════════════════════
#  SCALPING PROFIT TARGETS & SIZING (Forex & JPY)
# ════════════════════════════════════════════════
SCALP_TARGET_PROFIT_MIN     = 2.0    # Minimum scalp profit target
SCALP_TARGET_PROFIT_DEFAULT = 3.5    # JPY pairs profit banking ($3.50)
SCALP_TARGET_PROFIT_FOREX   = 2.2    # Standard Forex (EURUSD, GBPUSD) profit banking ($2.20)
SCALP_TARGET_PROFIT_MAX     = 5.0    # Hard ceiling ($5.00 max per scalp)
SCALP_MAX_LOSS_PER_TRADE    = 2.5    # Controlled stop loss risk ($1.50 - $2.50)
SCALP_FOREX_BE_TRIGGER      = 1.20   # Move to Breakeven once Forex is up +$1.20 (6 pips)
SCALP_JPY_BE_TRIGGER        = 2.00   # Move to Breakeven once JPY is up +$2.00

# ════════════════════════════════════════════════
#  BIG TRADES CONFIGURATION (XAUUSD / Gold Only)
# ════════════════════════════════════════════════
XAUUSD_BIG_TRADE_SL_MIN     = 12.0   # Min $12.00 point distance for stop loss (safe from noise)
XAUUSD_BIG_TRADE_TP_MIN     = 25.0   # Min $25.00 point distance for swing target ($25+ profit)
XAUUSD_BIG_TRADE_BE_TRIGGER = 8.0    # Move to Breakeven once Gold is up +$8.00 in profit
XAUUSD_BIG_TRADE_TP_CEILING = 35.0   # Big trade profit banking ceiling ($35.00)

# Lot sizing tuned for ~$200 accounts:
SCALP_DEFAULT_LOT_METALS = 0.01      # XAUUSD: 0.01 lot for safe swing risk ($12-$18 risk, $25-$45 target)
SCALP_DEFAULT_LOT_FOREX  = 0.02      # Forex: 0.02 lot for active scalping ($1.50 risk, $2.20-$3.50 target)


# ════════════════════════════════════════════════
#  RUNTIME STATE
# ════════════════════════════════════════════════
@dataclass
class TradingState:
    """Mutable runtime state — reset daily"""
    daily_pnl:        float = 0.0
    weekly_pnl:       float = 0.0
    monthly_pnl:      float = 0.0
    daily_trades:     int   = 0
    trading_enabled:  bool  = True
    trading_halted:   bool  = False
    halt_reason:      str   = ""
    last_trade_time:  str   = ""
    session_equity:   float = 0.0
    peak_equity:      float = 0.0

STATE = TradingState()

@dataclass
class DatabaseConfig:
    url: Optional[str] = os.getenv("DATABASE_URL")
    sqlite_path: str = DB_PATH

@dataclass
class SettingsWrapper:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8001"))
    reports_dir: str = REPORTS_DIR

    def __getattr__(self, name):
        import sys
        module = sys.modules[__name__]
        if hasattr(module, name):
            return getattr(module, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        import sys
        module = sys.modules.get(__name__)
        if module and hasattr(module, name):
            setattr(module, name, value)

settings = SettingsWrapper()
