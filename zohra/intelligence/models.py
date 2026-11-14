"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — INTELLIGENCE LAYER DATA MODELS                  ║
║       Shared dataclasses used across the intelligence ecosystem      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


# ════════════════════════════════════════════════════════════════
#  ENUMS
# ════════════════════════════════════════════════════════════════

class EventImpact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StrategyDeployment(str, Enum):
    DRAFT = "draft"
    TESTING = "testing"
    LIVE = "live"
    RETIRED = "retired"


class StrategyCategory(str, Enum):
    PRICE_ACTION = "price_action"
    SMART_MONEY = "smart_money"
    ICT = "ict"
    WYCKOFF = "wyckoff"
    BREAKOUT = "breakout"
    MOMENTUM = "momentum"
    TREND_FOLLOWING = "trend_following"
    SCALPING = "scalping"
    SWING = "swing"
    POSITION = "position"
    LONG_TERM = "long_term"
    MEAN_REVERSION = "mean_reversion"
    VOLATILITY = "volatility"
    OPTIONS = "options"
    FUTURES = "futures"
    HYBRID = "hybrid"
    AI_GENERATED = "ai_generated"


class WyckoffPhase(str, Enum):
    ACCUMULATION = "accumulation"
    MARKUP = "markup"
    DISTRIBUTION = "distribution"
    MARKDOWN = "markdown"
    UNKNOWN = "unknown"


class EnhancedRegime(str, Enum):
    STRONG_TREND = "strong_trend"
    WEAK_TREND = "weak_trend"
    BULL_MARKET = "bull_market"
    BEAR_MARKET = "bear_market"
    RANGING = "ranging"
    SIDEWAYS = "sideways"
    EXPANSION = "expansion"
    CONSOLIDATION = "consolidation"
    VOLATILITY_EXPANSION = "volatility_expansion"
    VOLATILITY_COMPRESSION = "volatility_compression"
    BREAKOUT_PHASE = "breakout_phase"
    REVERSAL_PHASE = "reversal_phase"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    PANIC_SELLING = "panic_selling"
    RECOVERY = "recovery"
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    LIQUIDITY_DRIVEN = "liquidity_driven"
    NEWS_DRIVEN = "news_driven"
    INSTITUTIONAL_ACTIVITY = "institutional_activity"


# ════════════════════════════════════════════════════════════════
#  PORTFOLIO
# ════════════════════════════════════════════════════════════════

@dataclass
class AllocationBreakdown:
    """Allocation percentages by category."""
    forex_pct: float = 0.0
    indian_market_pct: float = 0.0
    crypto_pct: float = 0.0
    cash_pct: float = 0.0
    by_sector: Dict[str, float] = field(default_factory=dict)
    by_currency: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RiskMetrics:
    """Portfolio-level risk statistics."""
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    var_95: float = 0.0          # Value at Risk (95% confidence)
    cvar_95: float = 0.0         # Conditional VaR
    max_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    expected_return: float = 0.0
    capital_efficiency: float = 0.0
    diversification_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PortfolioSnapshot:
    """Complete global portfolio state."""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    total_equity: float = 0.0
    total_margin_used: float = 0.0
    free_margin: float = 0.0
    open_positions: int = 0
    allocation: AllocationBreakdown = field(default_factory=AllocationBreakdown)
    risk_metrics: RiskMetrics = field(default_factory=RiskMetrics)
    health_score: float = 100.0   # 0–100
    correlation_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════════════════════════════════════════════════════
#  MULTI-TIMEFRAME
# ════════════════════════════════════════════════════════════════

@dataclass
class TimeframeResult:
    """Analysis result for a single timeframe."""
    timeframe: str = ""
    trend_direction: str = "NEUTRAL"    # BULLISH / BEARISH / NEUTRAL
    ema_aligned: bool = False
    rsi: float = 50.0
    adx: float = 0.0
    structure: str = "NONE"             # HH_HL / LH_LL / MIXED
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TimeframeAlignment:
    """Multi-timeframe confluence result."""
    symbol: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    results: List[TimeframeResult] = field(default_factory=list)
    aligned_count: int = 0
    total_analyzed: int = 0
    dominant_direction: str = "NEUTRAL"
    higher_tf_bias: str = "NEUTRAL"
    execution_timeframe: str = "M15"
    conflicts: List[str] = field(default_factory=list)
    combined_confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════════════════════════════════════════════════════
#  SMART MONEY
# ════════════════════════════════════════════════════════════════

@dataclass
class OrderBlock:
    """Detected order block."""
    type: str = "bullish"       # bullish / bearish / breaker / mitigation
    high: float = 0.0
    low: float = 0.0
    origin_index: int = 0
    strength: float = 0.0
    mitigated: bool = False


@dataclass
class FairValueGap:
    """Detected Fair Value Gap."""
    type: str = "bullish"       # bullish / bearish / inverse_bullish / inverse_bearish
    high: float = 0.0
    low: float = 0.0
    origin_index: int = 0
    filled: bool = False


@dataclass
class LiquidityZone:
    """Detected liquidity pool."""
    type: str = "internal"      # internal / external / sweep / void
    level: float = 0.0
    touched_count: int = 0
    swept: bool = False


@dataclass
class SmartMoneySignal:
    """Composite smart money analysis output."""
    symbol: str = ""
    timeframe: str = "M15"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    order_blocks: List[OrderBlock] = field(default_factory=list)
    fair_value_gaps: List[FairValueGap] = field(default_factory=list)
    liquidity_zones: List[LiquidityZone] = field(default_factory=list)
    bos_detected: bool = False
    choch_detected: bool = False
    premium_zone: bool = False
    discount_zone: bool = False
    wyckoff_phase: str = "unknown"
    displacement_detected: bool = False
    institutional_candle: bool = False
    confluence_count: int = 0
    confidence: float = 0.0
    bias: str = "NEUTRAL"       # BULLISH / BEARISH / NEUTRAL

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ════════════════════════════════════════════════════════════════
#  MACRO
# ════════════════════════════════════════════════════════════════

@dataclass
class MacroEvent:
    """A single economic calendar event."""
    event_id: str = ""
    title: str = ""
    country: str = ""
    currency: str = ""
    datetime_utc: str = ""
    impact: str = "low"         # low / medium / high / critical
    previous: str = ""
    forecast: str = ""
    actual: str = ""
    affected_assets: List[str] = field(default_factory=list)
    category: str = "general"   # interest_rate / inflation / employment / gdp / pmi / central_bank

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════════════════════════════════════════════════════
#  REGIME
# ════════════════════════════════════════════════════════════════

@dataclass
class RegimeAdjustments:
    """Dynamic adjustments based on detected regime."""
    risk_multiplier: float = 1.0
    position_size_multiplier: float = 1.0
    capital_allocation_multiplier: float = 1.0
    confidence_threshold: int = 70
    preferred_strategies: List[str] = field(default_factory=list)
    execution_frequency: str = "normal"    # aggressive / normal / conservative / paused

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegimeState:
    """Complete regime detection output."""
    symbol: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    primary_regime: str = "ranging"
    enhanced_regime: str = "sideways"
    confidence: float = 0.0
    volatility_state: str = "normal"     # low / normal / high / extreme
    adjustments: RegimeAdjustments = field(default_factory=RegimeAdjustments)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════════════════════════════════════════════════════
#  CROSS-MARKET
# ════════════════════════════════════════════════════════════════

@dataclass
class CrossMarketIntel:
    """Cross-market analysis output."""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    correlation_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    capital_rotation: Dict[str, str] = field(default_factory=dict)   # asset -> "inflow" / "outflow"
    risk_sentiment: str = "neutral"       # risk_on / risk_off / neutral
    global_sentiment_score: float = 50.0  # 0 (extreme fear) — 100 (extreme greed)
    institutional_flow: Dict[str, str] = field(default_factory=dict)
    dxy_trend: str = "NEUTRAL"
    vix_level: float = 0.0
    bond_yield_trend: str = "NEUTRAL"

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════════════════════════════════════════════════════
#  PIPELINE DECISION
# ════════════════════════════════════════════════════════════════

@dataclass
class PipelineDecision:
    """Full explainability trace for a trade decision."""
    decision_id: str = ""
    symbol: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    decision: str = "WAIT"             # BUY / SELL / WAIT / AVOID
    direction: str = "NEUTRAL"
    confidence: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_size: float = 0.0

    # Explainability trace
    mtf_alignment: Optional[TimeframeAlignment] = None
    smc_signal: Optional[SmartMoneySignal] = None
    macro_clearance: bool = True
    macro_events_nearby: List[str] = field(default_factory=list)
    regime: Optional[RegimeState] = None
    portfolio_exposure_ok: bool = True
    strategy_used: str = ""
    risk_approved: bool = False
    reasons: List[str] = field(default_factory=list)
    pipeline_stages: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            d[k] = v
        return d


# ════════════════════════════════════════════════════════════════
#  STRATEGY MARKETPLACE
# ════════════════════════════════════════════════════════════════

@dataclass
class StrategyPerformance:
    """Performance metrics for a strategy."""
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_rr: float = 0.0
    expectancy: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategyCard:
    """Marketplace metadata for a strategy."""
    name: str = ""
    version: str = "1.0.0"
    category: str = "price_action"
    description: str = ""
    author: str = "ZOHRA"
    supported_assets: List[str] = field(default_factory=list)
    supported_markets: List[str] = field(default_factory=list)
    supported_timeframes: List[str] = field(default_factory=list)
    risk_profile: str = "moderate"     # conservative / moderate / aggressive
    deployment: str = "draft"
    performance: StrategyPerformance = field(default_factory=StrategyPerformance)
    ai_rating: float = 0.0            # 0–5
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════════════════════════════════════════════════════
#  STRATEGY OPTIMIZER
# ════════════════════════════════════════════════════════════════

@dataclass
class OptimizationResult:
    """Output of a strategy optimization run."""
    optimization_id: str = ""
    strategy_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    method: str = "grid_search"       # grid_search / walk_forward / monte_carlo
    best_params: Dict[str, Any] = field(default_factory=dict)
    in_sample_sharpe: float = 0.0
    out_of_sample_sharpe: float = 0.0
    overfitting_score: float = 0.0     # 0 = no overfitting, 1 = fully overfit
    monte_carlo_pass: bool = False
    recommendations: List[str] = field(default_factory=list)
    improvement_pct: float = 0.0
    approved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
