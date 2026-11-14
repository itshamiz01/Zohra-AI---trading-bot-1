"""
╔══════════════════════════════════════════════════════════════════════╗
║         STRATEGY 7: SUPPORT & RESISTANCE REJECTION (XAUUSD)          ║
║         High-Probability Structural Pivot Reaction Scalper           ║
║                 Group: MEAN_REVERSION GROUP                          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np

from zohra.strategies.base_strategy import BaseStrategy, CandidateSignal
from zohra.core.market_regime import MarketRegime, RegimeReport
from zohra.core.enums import StrategyGroup, StrategyName
from zohra.indicators.support_resistance import check_sr_rejection
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.support_resistance")


class SupportResistanceStrategy(BaseStrategy):
    """
    Strategy 7: Trades objective rejections from scored horizontal support & resistance levels
    (PDH/PDL, session levels, pivot reaction clusters).
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.SR_REJECTION.value,
            strategy_group=StrategyGroup.MEAN_REVERSION.value,
            allowed_regimes=[
                MarketRegime.RANGING,
                MarketRegime.ROTATIONAL,
                MarketRegime.HIGH_VOLATILITY,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN
            ]
        )
        self.config = config or strategy_config.support_resistance

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < 25:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        sr_data = check_sr_rejection(df_entry, tolerance_usd=self.config.level_tolerance_usd)
        if not sr_data.get("rejection", False):
            return None

        if sr_data.get("score", 0) < self.config.min_level_score:
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        level_price = sr_data["level"]
        direction = sr_data["direction"]

        # In trending regimes, strictly take pro-trend rejections (never fade a trending market)
        regime = getattr(regime_report, "regime", None)
        if regime in (MarketRegime.TRENDING_UP, "trending_up") and direction != "BUY":
            return None
        if regime in (MarketRegime.TRENDING_DOWN, "trending_down") and direction != "SELL":
            return None

        # ─── SUPPORT REJECTION BUY ───
        if direction == "BUY":
            sl_price = round(level_price - (0.4 * atr_val), 3)
            stop_dist = max(close_p - sl_price, 0.8 * atr_val)
            tp_price = round(close_p + (stop_dist * self.config.min_risk_reward), 3)

            return CandidateSignal(
                strategy_name=self.name,
                strategy_group=self.strategy_group,
                symbol=strategy_config.gold_symbol,
                direction="BUY",
                entry_price=round(close_p, 3),
                stop_loss=sl_price,
                take_profit=tp_price,
                risk_reward=self.config.min_risk_reward,
                stop_distance_pips=round(stop_dist * 10.0, 1),
                setup_quality=sr_data["score"],
                confidence=regime_report.confidence,
                regime_match_score=90,
                volatility_score=80,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Support level rejection confirmed at {level_price:.2f} (Quality Score: {sr_data['score']}/100)",
                    f"Rejection wick confirmed ({sr_data.get('lower_wick_ratio', 0.35):.1%})",
                    f"Targeting +{self.config.min_risk_reward}R expansion to {tp_price:.2f}"
                ],
                metadata={"level": level_price, "sr_score": sr_data["score"]}
            )

        # ─── RESISTANCE REJECTION SELL ───
        elif direction == "SELL":
            sl_price = round(level_price + (0.4 * atr_val), 3)
            stop_dist = max(sl_price - close_p, 0.8 * atr_val)
            tp_price = round(close_p - (stop_dist * self.config.min_risk_reward), 3)

            return CandidateSignal(
                strategy_name=self.name,
                strategy_group=self.strategy_group,
                symbol=strategy_config.gold_symbol,
                direction="SELL",
                entry_price=round(close_p, 3),
                stop_loss=sl_price,
                take_profit=tp_price,
                risk_reward=self.config.min_risk_reward,
                stop_distance_pips=round(stop_dist * 10.0, 1),
                setup_quality=sr_data["score"],
                confidence=regime_report.confidence,
                regime_match_score=90,
                volatility_score=80,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Resistance level rejection confirmed at {level_price:.2f} (Quality Score: {sr_data['score']}/100)",
                    f"Rejection wick confirmed ({sr_data.get('upper_wick_ratio', 0.35):.1%})",
                    f"Targeting -{self.config.min_risk_reward}R expansion to {tp_price:.2f}"
                ],
                metadata={"level": level_price, "sr_score": sr_data["score"]}
            )

        return None
