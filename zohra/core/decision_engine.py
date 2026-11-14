"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — DECISION INTELLIGENCE ENGINE         ║
║  Coordinates Layers 1 - 6 Decision Pipeline         ║
╚══════════════════════════════════════════════════════╝
"""

import pandas as pd
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from zohra.core.enums import MarketRegime, Direction, StrategyName
from zohra.core.market_regime import regime_detector
from zohra.core.adaptive_scorer import adaptive_scorer
from zohra.strategies.mean_reversion import mean_reversion_strategy
from zohra.strategies.trend_following import trend_following_strategy
from zohra.strategies.breakout_strategy import breakout_strategy
from zohra.strategies.chart_pattern_strategy import chart_pattern_strategy

logger = logging.getLogger("zohra.decision_engine")


@dataclass
class DecisionExplanation:
    """Explainability record containing the exact rationale for a trade decision."""
    symbol: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    regime: str = "ranging"
    decision: str = "WAIT"             # BUY / SELL / WAIT / AVOID
    strategy_used: str = "none"
    confidence_score: int = 0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    scores_breakdown: Dict[str, float] = field(default_factory=dict)
    weights_used: Dict[str, float] = field(default_factory=dict)
    reasons_breakdown: Dict[str, str] = field(default_factory=dict)
    agreed_modules: List[str] = field(default_factory=list)
    disagreed_modules: List[str] = field(default_factory=list)
    summary_reason: str = "No trade condition identified."

    def to_dict(self) -> dict:
        return asdict(self)


class DecisionEngine:
    """
    Core DIE engine class coordinating Layer 1 to Layer 6 logic.
    Evaluates market data streams and generates structured decisions.
    """

    def __init__(self, min_score_threshold: int = 70):
        self.min_score_threshold = min_score_threshold

    def process_data(self, df_m5: pd.DataFrame, df_m15: pd.DataFrame, df_h1: pd.DataFrame,
                     symbol: str) -> DecisionExplanation:
        """
        Runs the 6-layer pipeline for a single symbol.
        Returns a DecisionExplanation containing the trade decision and audit trail.
        """
        # ─── Layer 1: Market Regime Detection ───
        # Use H1/M15 combination for regime (primarily M15 for execution)
        regime_info = regime_detector.detect_with_details(df_m15)
        regime = regime_info['regime']

        # Pre-emptively AVOID high-risk regimes
        if regime in (MarketRegime.NEWS_DRIVEN, MarketRegime.LOW_LIQUIDITY):
            return DecisionExplanation(
                symbol=symbol,
                regime=regime.value,
                decision="AVOID",
                summary_reason=f"Avoided: High-risk market state ({regime.value}) detected."
            )

        # ─── Layer 2: Strategy Selection & Route ───
        # Determine candidate strategies based on regime
        candidate_strategies = []
        if regime == MarketRegime.TRENDING:
            candidate_strategies = [
                (trend_following_strategy, StrategyName.TREND_FOLLOWING.value),
                (chart_pattern_strategy, StrategyName.CHART_PATTERNS.value),
            ]
        elif regime == MarketRegime.RANGING:
            candidate_strategies = [
                (mean_reversion_strategy, StrategyName.MEAN_REVERSION.value),
                (chart_pattern_strategy, StrategyName.CHART_PATTERNS.value),
            ]
        elif regime in (MarketRegime.BREAKOUT, MarketRegime.HIGH_VOLATILITY):
            candidate_strategies = [
                (breakout_strategy, StrategyName.BREAKOUT.value),
                (chart_pattern_strategy, StrategyName.CHART_PATTERNS.value),
            ]

        if not candidate_strategies:
            return DecisionExplanation(
                symbol=symbol,
                regime=regime.value,
                decision="WAIT",
                summary_reason=f"No matching active strategies for regime: {regime.value}"
            )

        # ─── Layer 3 & 4: Confluence & Scoring ───
        best_signal = None
        best_confluence = None
        best_strategy_name = "none"

        for strat_inst, strat_name in candidate_strategies:
            # Generate strategy signals
            # Trend following and breakout run on M15, mean reversion runs on M15/M5
            df_to_use = df_m5 if strat_name == StrategyName.MEAN_REVERSION.value else df_m15
            sig = strat_inst.generate_signal(df_to_use, symbol)
            
            if sig:
                # Evaluate confluence and adaptive weights
                confl = adaptive_scorer.evaluate_confluence(
                    df_to_use, sig['direction'], symbol, regime, strat_name
                )
                
                if best_signal is None or confl['final_score'] > best_confluence['final_score']:
                    best_signal = sig
                    best_confluence = confl
                    best_strategy_name = strat_name

        if not best_signal:
            return DecisionExplanation(
                symbol=symbol,
                regime=regime.value,
                decision="WAIT",
                summary_reason="Scanning complete: strategies active but no setup triggers generated."
            )

        # ─── Layer 5: Trade Decision ───
        score = best_confluence['final_score']
        direction = best_signal['direction']
        
        # Split modules into agreed (score >= 50) and disagreed (score < 50)
        agreed = []
        disagreed = []
        for mod, mod_score in best_confluence['scores'].items():
            if mod_score >= 50:
                agreed.append(mod)
            else:
                disagreed.append(mod)

        # Check thresholds
        if score >= self.min_score_threshold:
            # Check if correlation score is severely low, which means high exposure risk
            if best_confluence['scores'].get('correlation', 100) < 30:
                decision = "AVOID"
                summary = f"Avoided: Setup formed but rejected due to high asset correlation risk."
            else:
                decision = "BUY" if direction == "LONG" else "SELL"
                summary = f"Execution Trigger: {decision} order approved by strategy {best_strategy_name} with score {score}/100."
        elif score >= 55:
            decision = "WAIT"
            summary = f"Wait: Setup identified, but confidence score {score}/100 below execution threshold ({self.min_score_threshold})."
        else:
            decision = "AVOID"
            summary = f"Avoided: Opportunity scored too low ({score}/100) for safe market entry."

        # ─── Layer 6: Packaging Explainability ───
        explanation = DecisionExplanation(
            symbol=symbol,
            regime=regime.value,
            decision=decision,
            strategy_used=best_strategy_name,
            confidence_score=score,
            entry_price=best_signal['entry_price'],
            stop_loss=best_signal['stop_loss'],
            take_profit=best_signal['take_profit'],
            scores_breakdown=best_confluence['scores'],
            weights_used=best_confluence['weights'],
            reasons_breakdown=best_confluence['reasons'],
            agreed_modules=agreed,
            disagreed_modules=disagreed,
            summary_reason=summary
        )

        return explanation


# Singleton
decision_engine = DecisionEngine()
