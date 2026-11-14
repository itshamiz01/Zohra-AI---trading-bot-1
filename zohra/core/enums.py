"""Domain enumerations for the Zohra trading engine."""

from enum import Enum


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    BUY = "BUY"
    SELL = "SELL"


class MarketRegime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    TRENDING = "trending"
    RANGING = "ranging"
    ROTATIONAL = "rotational"
    BREAKOUT_EXPANSION = "breakout_expansion"
    BREAKOUT = "breakout"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    NEWS_OR_ABNORMAL_VOLATILITY = "news_or_abnormal_volatility"
    NEWS_DRIVEN = "news_driven"
    UNCLEAR = "unclear"


class TradeQuality(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    REJECT = "REJECT"


class Session(str, Enum):
    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"
    OFF = "off"


class StrategyGroup(str, Enum):
    TREND = "TREND"
    MEAN_REVERSION = "MEAN_REVERSION"
    STRUCTURE_SMC = "STRUCTURE_SMC"
    BREAKOUT_VOLATILITY = "BREAKOUT_VOLATILITY"


class StrategyName(str, Enum):
    # ─── 15 APPROVED SCALPING STRATEGIES ───
    EMA_PULLBACK = "ema_pullback"
    VWAP_MEAN_REVERSION = "vwap_mean_reversion"
    LIQUIDITY_MSS = "liquidity_mss"
    BREAKOUT = "breakout"
    BOLLINGER_RSI = "bollinger_rsi"
    FIBONACCI_PULLBACK = "fibonacci_pullback"
    SR_REJECTION = "sr_rejection"
    SUPPLY_DEMAND = "supply_demand"
    FVG_RETRACEMENT = "fvg_retracement"
    ORDER_BLOCK = "order_block"
    VOLUME_BREAKOUT = "volume_breakout"
    ATR_EXPANSION = "atr_expansion"
    MOMENTUM_CONTINUATION = "momentum_continuation"
    MTF_ALIGNMENT = "mtf_alignment"
    FALSE_BREAKOUT = "false_breakout"

    # Legacy / Auxiliary identifiers
    EMA_ATR = "ema_atr"
    ZOHRA_SMC = "zohra_smc"
    ZOHRA_V5 = "zohra_v5"
    GOLD_SCALP = "gold_scalp"
    SCALP_M5 = "scalp_m5"
    MEAN_REVERSION = "mean_reversion"
    TREND_FOLLOWING = "trend_following"
    CHART_PATTERNS = "chart_patterns"
    MANUAL = "manual"


class NewsStatus(str, Enum):
    CLEAR = "clear"
    UPCOMING = "upcoming"
    ACTIVE = "active"
    POST_NEWS = "post_news"
    BLACKOUT = "blackout"
    HIGH_IMPACT = "high_impact"
    UNKNOWN = "unknown"
