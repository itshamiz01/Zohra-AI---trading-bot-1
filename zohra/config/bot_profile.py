"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — BOT SPECIALIZATION PROFILES                     ║
║           SCALPING-FIRST WITH SWING-OPPORTUNITY AWARENESS            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import os

from zohra.core.enums import MarketRegime, StrategyName, StrategyGroup


@dataclass
class BotSpecializationProfile:
    """
    Complete configuration for an independently specialized ZOHRA bot instance.
    Configured for Scalping-First execution with secondary Swing detection.
    """
    bot_id: str
    bot_name: str
    bot_role: str
    specialization_description: str
    allowed_symbols: List[str] = field(default_factory=lambda: ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"])

    # Strategy specialization
    enabled_strategy_groups: List[str] = field(default_factory=list)
    enabled_strategies: List[str] = field(default_factory=list)

    # Timeframe hierarchy: M5 entry with M15 structure & H1 macro guidance
    primary_timeframes: List[str] = field(default_factory=lambda: ["H1", "M15", "M5", "M1"])
    entry_timeframe: str = "M5"
    structure_timeframe: str = "M15"
    macro_timeframe: str = "H1"

    # Market regime routing & priority
    allowed_regimes: List[str] = field(default_factory=list)
    regime_priority_map: Dict[str, str] = field(default_factory=dict)

    # Execution & Confidence thresholds (Tuned for active Scalping)
    min_confidence: int = 60
    min_risk_reward: float = 1.2
    min_confirmations: int = 1          # 1 clear setup is enough to scalp; multi-confirmations boost grade to A+
    min_strategy_groups: int = 1

    # Risk & Session limits
    max_open_positions: int = 3
    max_risk_per_trade_pct: float = 0.01
    max_daily_trades: int = 30
    max_trades_per_session: int = 12
    max_consecutive_losses: int = 4
    cooldown_seconds: int = 60          # 60s cooldown between scalps

    # Environmental filters
    max_spread_pips: float = 4.0
    news_blackout_minutes_before: int = 15
    news_blackout_minutes_after: int = 15
    session_filter: List[str] = field(default_factory=lambda: ["Asian", "London", "NewYork", "Overlap"])

    def is_strategy_enabled(self, strategy_name: str) -> bool:
        """Check if a strategy is part of this bot's specialized portfolio."""
        return strategy_name in self.enabled_strategies

    def get_regime_priority(self, regime: str) -> str:
        """Returns the priority level for the given market regime."""
        clean_regime = regime.lower().strip()
        if clean_regime in self.regime_priority_map:
            return self.regime_priority_map[clean_regime]
        # A new or unclassified market regime must not silently become
        # tradable for a specialized bot.
        return "BLOCKED"

    def is_regime_tradable(self, regime: str) -> bool:
        """Returns True if the bot is permitted to trade in this market regime."""
        priority = self.get_regime_priority(regime)
        return priority in ("HIGH", "MEDIUM", "LOW")


# ════════════════════════════════════════════════════════════════════════
#  BOT 1 — TREND & MOMENTUM SCALPER (Primary: Scalp, Secondary: Swing)
# ════════════════════════════════════════════════════════════════════════
BOT_1_TREND_PROFILE = BotSpecializationProfile(
    bot_id="BOT_1_TREND",
    bot_name="Bot A (Trend & Momentum Scalper)",
    bot_role="Trend & Momentum Scalper",
    specialization_description=(
        "Captures fast trend pullbacks, micro-momentum continuations, and MTF trend alignment scalps. "
        "Also captures macro swing continuation runs when available."
    ),
    allowed_symbols=["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"],
    enabled_strategy_groups=[
        StrategyGroup.TREND.value
    ],
    enabled_strategies=[
        StrategyName.EMA_PULLBACK.value,
        StrategyName.FIBONACCI_PULLBACK.value,
        StrategyName.MTF_ALIGNMENT.value,
        StrategyName.MOMENTUM_CONTINUATION.value,
        StrategyName.BREAKOUT.value,
    ],
    primary_timeframes=["H1", "M15", "M5", "M1"],
    macro_timeframe="H1",
    structure_timeframe="M15",
    entry_timeframe="M5",
    allowed_regimes=[
        "trending_up",
        "trending_down",
        "trending",
        "breakout_expansion",
        "breakout",
        "structural_transition",
    ],
    regime_priority_map={
        "trending_up": "HIGH",
        "trending_down": "HIGH",
        "trending": "HIGH",
        # Breakout detection belongs primarily to the structure specialist.
        # The trend bot may participate only after continuation confirmation.
        "breakout_expansion": "MEDIUM",
        "breakout": "MEDIUM",
        "structural_transition": "MEDIUM",
        "ranging": "BLOCKED",
        "rotational": "BLOCKED",
        "unclear": "BLOCKED",
        "low_liquidity": "BLOCKED",
        "news_or_abnormal_volatility": "BLOCKED",
    },
    min_confidence=60,
    min_risk_reward=1.2,
    min_confirmations=1,
    min_strategy_groups=1,
    max_open_positions=3,
    max_risk_per_trade_pct=0.01,
    max_daily_trades=30,
    cooldown_seconds=60,
    max_spread_pips=4.0
)


# ════════════════════════════════════════════════════════════════════════
#  BOT 2 — MEAN REVERSION & REVERSAL SCALPER
# ════════════════════════════════════════════════════════════════════════
BOT_2_REVERSAL_PROFILE = BotSpecializationProfile(
    bot_id="BOT_2_REVERSAL",
    bot_name="Bot B (Reversal & VWAP Scalper)",
    bot_role="Mean Reversion & Reversal Scalper",
    specialization_description=(
        "Executes rapid mean reversion scalps, VWAP bounce/rejections, RSI overextended snaps, "
        "and boundary reversals across ranging and trending pullback conditions."
    ),
    allowed_symbols=["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"],
    enabled_strategy_groups=[
        StrategyGroup.MEAN_REVERSION.value
    ],
    enabled_strategies=[
        StrategyName.VWAP_MEAN_REVERSION.value,
        StrategyName.BOLLINGER_RSI.value,
        StrategyName.SR_REJECTION.value,
        StrategyName.FALSE_BREAKOUT.value,
        StrategyName.ATR_EXPANSION.value,
    ],
    primary_timeframes=["M15", "M5", "M1"],
    macro_timeframe="M15",
    structure_timeframe="M5",
    entry_timeframe="M5",
    allowed_regimes=[
        "ranging",
        "rotational",
        "high_volatility",
        "structural_transition",
    ],
    regime_priority_map={
        "ranging": "HIGH",
        "rotational": "HIGH",
        "high_volatility": "HIGH",
        "structural_transition": "MEDIUM",
        "trending_up": "BLOCKED",
        "trending_down": "BLOCKED",
        "trending": "BLOCKED",
        "breakout_expansion": "BLOCKED",
        "breakout": "BLOCKED",
        "unclear": "BLOCKED",
        "low_liquidity": "BLOCKED",
        "news_or_abnormal_volatility": "BLOCKED",
    },
    min_confidence=60,
    min_risk_reward=1.2,
    min_confirmations=1,
    min_strategy_groups=1,
    max_open_positions=3,
    max_risk_per_trade_pct=0.01,
    max_daily_trades=30,
    cooldown_seconds=60,
    max_spread_pips=3.5
)


# ════════════════════════════════════════════════════════════════════════
#  BOT 3 — STRUCTURE & BREAKOUT SCALPER
# ════════════════════════════════════════════════════════════════════════
BOT_3_STRUCTURE_PROFILE = BotSpecializationProfile(
    bot_id="BOT_3_STRUCTURE",
    bot_name="Bot C (Structure & Breakout Scalper)",
    bot_role="Structure & Breakout Scalper",
    specialization_description=(
        "Captures fast liquidity sweep scalps, Fair Value Gap taps, Order Block reactions, "
        "and volatility range expansion breakouts on intraday charts."
    ),
    allowed_symbols=["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"],
    enabled_strategy_groups=[
        StrategyGroup.STRUCTURE_SMC.value,
        StrategyGroup.BREAKOUT_VOLATILITY.value
    ],
    enabled_strategies=[
        StrategyName.LIQUIDITY_MSS.value,
        StrategyName.SUPPLY_DEMAND.value,
        StrategyName.FVG_RETRACEMENT.value,
        StrategyName.ORDER_BLOCK.value,
        StrategyName.VOLUME_BREAKOUT.value,
    ],
    primary_timeframes=["H1", "M15", "M5", "M1"],
    macro_timeframe="H1",
    structure_timeframe="M15",
    entry_timeframe="M5",
    allowed_regimes=[
        "breakout_expansion",
        "breakout",
        "structural_transition",
        "high_volatility",
        "trending_up",
        "trending_down",
        "trending",
        "ranging",
        "rotational",
        "unclear",
    ],
    regime_priority_map={
        "breakout_expansion": "HIGH",
        "breakout": "HIGH",
        "structural_transition": "HIGH",
        "high_volatility": "HIGH",
        "trending_up": "HIGH",
        "trending_down": "HIGH",
        "trending": "HIGH",
        # A non-breaking range is not a structure breakout setup. Keep this
        # available only as a low-priority confirmation, never a primary trade.
        "ranging": "LOW",
        "rotational": "MEDIUM",
        "unclear": "MEDIUM",
        "low_liquidity": "BLOCKED",
        "news_or_abnormal_volatility": "BLOCKED",
    },
    min_confidence=60,
    min_risk_reward=1.2,
    min_confirmations=1,
    min_strategy_groups=1,
    max_open_positions=3,
    max_risk_per_trade_pct=0.01,
    max_daily_trades=30,
    cooldown_seconds=60,
    max_spread_pips=4.0
)


# ════════════════════════════════════════════════════════════════════════
#  ZOHRA UNIFIED — ALL 15 STRATEGIES, 3 MT5 ACCOUNTS
#  Centralized intelligence, isolated execution
# ════════════════════════════════════════════════════════════════════════
ZOHRA_UNIFIED_PROFILE = BotSpecializationProfile(
    bot_id="ZOHRA_UNIFIED",
    bot_name="ZOHRA Unified Trading OS",
    bot_role="Unified Multi-Strategy Engine",
    specialization_description=(
        "Centralized 15-strategy intelligence engine running ALL strategies "
        "across TREND, MEAN_REVERSION, STRUCTURE_SMC, and BREAKOUT_VOLATILITY groups. "
        "Signals fan out to 3 isolated MT5 account workers for execution."
    ),
    allowed_symbols=["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"],
    enabled_strategy_groups=[
        StrategyGroup.TREND.value,
        StrategyGroup.MEAN_REVERSION.value,
        StrategyGroup.STRUCTURE_SMC.value,
        StrategyGroup.BREAKOUT_VOLATILITY.value,
    ],
    enabled_strategies=[
        # ─── Bot 1 (Trend & Momentum) strategies ───
        StrategyName.EMA_PULLBACK.value,
        StrategyName.FIBONACCI_PULLBACK.value,
        StrategyName.MTF_ALIGNMENT.value,
        StrategyName.MOMENTUM_CONTINUATION.value,
        # ─── Bot 2 (Mean Reversion & Reversal) strategies ───
        StrategyName.VWAP_MEAN_REVERSION.value,
        StrategyName.BOLLINGER_RSI.value,
        StrategyName.SR_REJECTION.value,
        StrategyName.FALSE_BREAKOUT.value,
        # ─── Bot 3 (Structure & Breakout) strategies ───
        StrategyName.LIQUIDITY_MSS.value,
        StrategyName.SUPPLY_DEMAND.value,
        StrategyName.FVG_RETRACEMENT.value,
        StrategyName.ORDER_BLOCK.value,
        StrategyName.BREAKOUT.value,
        StrategyName.VOLUME_BREAKOUT.value,
        StrategyName.ATR_EXPANSION.value,
    ],
    primary_timeframes=["H4", "H1", "M15", "M5", "M1"],
    macro_timeframe="H1",
    structure_timeframe="M15",
    entry_timeframe="M5",
    allowed_regimes=[
        "trending_up",
        "trending_down",
        "trending",
        "breakout_expansion",
        "breakout",
        "structural_transition",
        "high_volatility",
        "ranging",
        "rotational",
        "unclear",
    ],
    regime_priority_map={
        "trending_up": "HIGH",
        "trending_down": "HIGH",
        "trending": "HIGH",
        "breakout_expansion": "HIGH",
        "breakout": "HIGH",
        "structural_transition": "HIGH",
        "high_volatility": "HIGH",
        "ranging": "MEDIUM",
        "rotational": "MEDIUM",
        "unclear": "MEDIUM",
        "low_liquidity": "BLOCKED",
        "news_or_abnormal_volatility": "BLOCKED",
    },
    min_confidence=60,
    min_risk_reward=1.2,
    min_confirmations=1,
    min_strategy_groups=1,
    max_open_positions=5,       # Higher cap for unified system (across all accounts)
    max_risk_per_trade_pct=0.01,
    max_daily_trades=50,        # 50 total across all accounts
    cooldown_seconds=30,        # Fast 30s cooldown for short-term scalping
    max_spread_pips=4.0
)


# Dictionary mapping for dynamic selection
PROFILES_BY_ROLE: Dict[str, BotSpecializationProfile] = {
    "BOT_1_TREND": BOT_1_TREND_PROFILE,
    "BOT_2_REVERSAL": BOT_2_REVERSAL_PROFILE,
    "BOT_3_STRUCTURE": BOT_3_STRUCTURE_PROFILE,
}

SPECIALIZATION_PROFILES: Dict[str, BotSpecializationProfile] = {
    "BOT_1_TREND": BOT_1_TREND_PROFILE,
    "BOT_2_REVERSAL": BOT_2_REVERSAL_PROFILE,
    "BOT_3_STRUCTURE": BOT_3_STRUCTURE_PROFILE,
    "ZOHRA_UNIFIED": ZOHRA_UNIFIED_PROFILE,
    # Aliases
    "TREND": BOT_1_TREND_PROFILE,
    "REVERSAL": BOT_2_REVERSAL_PROFILE,
    "STRUCTURE": BOT_3_STRUCTURE_PROFILE,
    "BREAKOUT": BOT_3_STRUCTURE_PROFILE,
    "UNIFIED": ZOHRA_UNIFIED_PROFILE,
}


def get_active_bot_profile() -> BotSpecializationProfile:
    """
    Returns the specialization profile configured for this process.
    Determined via BOT_ID environment variable (defaults to BOT_1_TREND).
    """
    bot_id = os.getenv("BOT_ID", "BOT_1_TREND").upper().strip()
    profile = SPECIALIZATION_PROFILES.get(bot_id, BOT_1_TREND_PROFILE)
    return profile


def load_bot_profile(role_or_id: Optional[str] = None) -> BotSpecializationProfile:
    """Loads bot profile by role or ID, defaulting to environment config."""
    if role_or_id:
        clean = str(role_or_id).upper().strip()
        if clean in SPECIALIZATION_PROFILES:
            return SPECIALIZATION_PROFILES[clean]
        for k, v in SPECIALIZATION_PROFILES.items():
            if k in clean or clean in k:
                return v
    return get_active_bot_profile()


# ════════════════════════════════════════════════════════════════════════
#  3-ACCOUNT STRATEGY MAPPING (5 STRATEGIES PER ACCOUNT)
# ════════════════════════════════════════════════════════════════════════
ACCOUNT_BOT_PROFILE_MAP: Dict[str, BotSpecializationProfile] = {
    "account_01": BOT_1_TREND_PROFILE,
    "account_02": BOT_2_REVERSAL_PROFILE,
    "account_03": BOT_3_STRUCTURE_PROFILE,
}

STRATEGY_TO_ACCOUNT_MAP: Dict[str, str] = {
    # Account 01 — Bot 1 (Trend & Momentum) [5 Strategies]
    StrategyName.EMA_PULLBACK.value: "account_01",
    StrategyName.FIBONACCI_PULLBACK.value: "account_01",
    StrategyName.MTF_ALIGNMENT.value: "account_01",
    StrategyName.MOMENTUM_CONTINUATION.value: "account_01",
    StrategyName.BREAKOUT.value: "account_01",

    # Account 02 — Bot 2 (Mean Reversion & Volatility) [5 Strategies]
    StrategyName.VWAP_MEAN_REVERSION.value: "account_02",
    StrategyName.BOLLINGER_RSI.value: "account_02",
    StrategyName.SR_REJECTION.value: "account_02",
    StrategyName.FALSE_BREAKOUT.value: "account_02",
    StrategyName.ATR_EXPANSION.value: "account_02",

    # Account 03 — Bot 3 (Structure & Smart Money Concepts) [5 Strategies]
    StrategyName.LIQUIDITY_MSS.value: "account_03",
    StrategyName.SUPPLY_DEMAND.value: "account_03",
    StrategyName.FVG_RETRACEMENT.value: "account_03",
    StrategyName.ORDER_BLOCK.value: "account_03",
    StrategyName.VOLUME_BREAKOUT.value: "account_03",
}

def get_account_for_strategy(strategy_id: str) -> Optional[str]:
    """Get the account ID assigned to execute this strategy."""
    if not strategy_id:
        return None
    return STRATEGY_TO_ACCOUNT_MAP.get(str(strategy_id).lower().strip())

def get_profile_for_account(account_id: str) -> BotSpecializationProfile:
    """Get the specialization profile assigned to this account."""
    clean_id = str(account_id).lower().strip()
    return ACCOUNT_BOT_PROFILE_MAP.get(clean_id, ZOHRA_UNIFIED_PROFILE)
