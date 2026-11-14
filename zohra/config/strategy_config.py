"""
╔══════════════════════════════════════════════════════════════════════╗
║             ZOHRA — 15-STRATEGY CONFIGURATION PARAMETERS             ║
║            Institutional Gold (XAUUSD) Confluence Scalper            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


# ─── GROUP 1: TREND STRATEGIES ───

@dataclass
class EmaPullbackConfig:
    enabled: bool = True
    fast_ema_period: int = 9
    slow_ema_period: int = 21
    trend_ema_period: int = 50
    min_ema_slope: float = 0.15
    min_adx: float = 22.0
    max_pullback_distance_atr: float = 1.5
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"
    htf_timeframe: str = "M15"
    fast_ema: int = 9
    slow_ema: int = 21
    trend_ema: int = 50


@dataclass
class FibonacciPullbackConfig:
    enabled: bool = True
    swing_lookback: int = 30
    min_fib_level: float = 0.382
    max_fib_level: float = 0.618
    deep_fib_level: float = 0.786
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


@dataclass
class MtfAlignmentConfig:
    enabled: bool = True
    context_timeframe: str = "M15"
    structure_timeframe: str = "M5"
    trigger_timeframe: str = "M1"
    require_all_three: bool = False       # If false, M15 + M5 alignment suffices
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5


@dataclass
class MomentumContinuationConfig:
    enabled: bool = True
    min_body_ratio: float = 0.65
    min_atr_multiple: float = 1.3
    max_pullback_ratio: float = 0.50
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 2.0
    timeframe: str = "M5"


# ─── GROUP 2: MEAN-REVERSION STRATEGIES ───

@dataclass
class VwapMeanReversionConfig:
    enabled: bool = True
    min_stretch_atr: float = 1.5
    min_vwap_distance_atr: float = 1.5
    max_vwap_slope: float = 0.25
    max_adx_trend: float = 25.0
    max_adx_threshold: float = 25.0
    min_rejection_wick_ratio: float = 0.35
    target_vwap: bool = True
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


@dataclass
class BollingerRsiConfig:
    enabled: bool = True
    bb_period: int = 20
    bb_std_dev: float = 2.0
    bb_std: float = 2.0
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    max_adx_trend: float = 25.0
    max_adx_filter: float = 25.0
    min_reversal_confirmation: bool = True
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


@dataclass
class SupportResistanceConfig:
    enabled: bool = True
    level_tolerance_usd: float = 1.2
    min_level_score: int = 60
    min_rejection_wick_ratio: float = 0.35
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


# ─── GROUP 3: STRUCTURE / SMC STRATEGIES ───

@dataclass
class LiquidityMssConfig:
    enabled: bool = True
    sweep_lookback_bars: int = 25
    swing_lookback: int = 20
    min_sweep_reclaim_pips: float = 1.0
    mss_confirmation_bars: int = 5
    retest_required: bool = False
    min_risk_reward: float = 2.0
    stop_buffer_pips: float = 2.0
    timeframe: str = "M5"


@dataclass
class SupplyDemandConfig:
    enabled: bool = True
    min_displacement_atr: float = 1.3
    max_touch_count: int = 3
    require_fresh: bool = False          # Accept FRESH or TESTED (<= 3 touches)
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


@dataclass
class FvgRetracementConfig:
    enabled: bool = True
    min_gap_atr_ratio: float = 0.25
    lookback_bars: int = 30
    require_unmitigated: bool = True
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


@dataclass
class OrderBlockConfig:
    enabled: bool = True
    min_displacement_atr: float = 1.2
    lookback_bars: int = 35
    require_unmitigated: bool = True
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


@dataclass
class FalseBreakoutConfig:
    enabled: bool = True
    tolerance_usd: float = 1.5
    reclaim_bars: int = 3
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 1.5
    timeframe: str = "M5"


# ─── GROUP 4: BREAKOUT / VOLATILITY STRATEGIES ───

@dataclass
class BreakoutConfig:
    enabled: bool = True
    orb_session_start_hour_utc: int = 13
    orb_duration_minutes: int = 30
    donchian_period: int = 20
    min_atr_expansion_ratio: float = 1.2
    min_breakout_candle_body_ratio: float = 0.5
    max_trades_per_range: int = 1
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 2.0
    timeframe: str = "M5"


@dataclass
class VolumeBreakoutConfig:
    enabled: bool = True
    min_rvol: float = 1.35
    range_period: int = 20
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 2.0
    timeframe: str = "M5"


@dataclass
class AtrCompressionExpansionConfig:
    enabled: bool = True
    compression_bars: int = 5
    max_compression_ratio: float = 0.82
    min_expansion_ratio: float = 1.15
    min_risk_reward: float = 1.5
    stop_buffer_pips: float = 2.0
    timeframe: str = "M5"


# ─── CONFLUENCE ENGINE & ARBITRATION CONFIG ───

@dataclass
class ConfluenceEngineConfig:
    min_confirmations: int = 3           # Minimum 3 valid strategies in same direction
    min_strategy_groups: int = 2         # Mode A: minimum 2 independent strategy groups
    confluence_mode: str = "MODE_A"      # "MODE_A" (2 groups) or "MODE_B" (3 groups)
    min_exec_score: int = 65             # Minimum score to qualify for execution
    grade_a_plus_min: int = 90
    grade_a_min: int = 80
    grade_b_min: int = 70
    grade_c_min: int = 60
    allow_c_grade: bool = True
    dominance_margin_pts: int = 15       # BUY_SCORE - SELL_SCORE >= 15 pts for directional dominance
    cooldown_seconds_after_trade: int = 120
    cooldown_seconds: int = 120
    max_trades_per_session: int = 10
    max_daily_trades: int = 20
    max_trades_per_day: int = 20
    max_spread_pips: float = 4.5
    signal_max_age_seconds: int = 300


@dataclass
class MarketRegimeConfig:
    adx_trend_threshold: float = 22.0
    adx_strong_trend_threshold: float = 30.0
    ema_slope_trending_threshold: float = 0.20
    bollinger_bandwidth_compression_threshold: float = 0.0035
    atr_expansion_threshold: float = 1.20
    min_confidence_score: int = 65
    adx_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    vol_sma_period: int = 20
    trend_adx_min: float = 20.0
    strong_trend_adx: float = 28.0
    high_volatility_atr_mult: float = 1.4
    low_liquidity_vol_ratio: float = 0.35
    news_body_atr_mult: float = 2.8


# ─── MASTER CONTAINER CONFIG ───

@dataclass
class XauusdEngineConfig:
    gold_symbol: str = "XAUUSD"
    # Trend
    ema_pullback: EmaPullbackConfig = field(default_factory=EmaPullbackConfig)
    fibonacci_pullback: FibonacciPullbackConfig = field(default_factory=FibonacciPullbackConfig)
    mtf_alignment: MtfAlignmentConfig = field(default_factory=MtfAlignmentConfig)
    momentum: MomentumContinuationConfig = field(default_factory=MomentumContinuationConfig)
    # Mean-Reversion
    vwap_reversion: VwapMeanReversionConfig = field(default_factory=VwapMeanReversionConfig)
    bollinger_rsi: BollingerRsiConfig = field(default_factory=BollingerRsiConfig)
    support_resistance: SupportResistanceConfig = field(default_factory=SupportResistanceConfig)
    # Structure / SMC
    liquidity_mss: LiquidityMssConfig = field(default_factory=LiquidityMssConfig)
    supply_demand: SupplyDemandConfig = field(default_factory=SupplyDemandConfig)
    fvg: FvgRetracementConfig = field(default_factory=FvgRetracementConfig)
    order_block: OrderBlockConfig = field(default_factory=OrderBlockConfig)
    false_breakout: FalseBreakoutConfig = field(default_factory=FalseBreakoutConfig)
    # Breakout / Volatility
    breakout: BreakoutConfig = field(default_factory=BreakoutConfig)
    volume_breakout: VolumeBreakoutConfig = field(default_factory=VolumeBreakoutConfig)
    atr_expansion: AtrCompressionExpansionConfig = field(default_factory=AtrCompressionExpansionConfig)
    # Engines
    regime: MarketRegimeConfig = field(default_factory=MarketRegimeConfig)
    confluence: ConfluenceEngineConfig = field(default_factory=ConfluenceEngineConfig)
    arbitrator: ConfluenceEngineConfig = field(default_factory=ConfluenceEngineConfig)


# Master instance & singletons
strategy_config = XauusdEngineConfig()
EMA_PULLBACK_CONFIG = strategy_config.ema_pullback
FIBONACCI_CONFIG = strategy_config.fibonacci_pullback
MTF_ALIGNMENT_CONFIG = strategy_config.mtf_alignment
MOMENTUM_CONFIG = strategy_config.momentum
VWAP_MEAN_REVERSION_CONFIG = strategy_config.vwap_reversion
BOLLINGER_RSI_CONFIG = strategy_config.bollinger_rsi
SR_CONFIG = strategy_config.support_resistance
LIQUIDITY_MSS_CONFIG = strategy_config.liquidity_mss
SUPPLY_DEMAND_CONFIG = strategy_config.supply_demand
FVG_CONFIG = strategy_config.fvg
ORDER_BLOCK_CONFIG = strategy_config.order_block
FALSE_BREAKOUT_CONFIG = strategy_config.false_breakout
BREAKOUT_CONFIG = strategy_config.breakout
VOLUME_BREAKOUT_CONFIG = strategy_config.volume_breakout
ATR_EXPANSION_CONFIG = strategy_config.atr_expansion
REGIME_ENGINE_CONFIG = strategy_config.regime
CONFLUENCE_ENGINE_CONFIG = strategy_config.confluence
SIGNAL_ARBITRATION_CONFIG = strategy_config.arbitrator
