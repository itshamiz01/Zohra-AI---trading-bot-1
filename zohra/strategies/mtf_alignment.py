"""
╔══════════════════════════════════════════════════════════════════════╗
║         STRATEGY 14: MULTI-TIMEFRAME TREND ALIGNMENT (XAUUSD)         ║
║          Hierarchical M15 Bias + M5 Structure + M1 Trigger           ║
║                     Group: TREND GROUP                               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np

from zohra.strategies.base_strategy import BaseStrategy, CandidateSignal
from zohra.core.market_regime import MarketRegime, RegimeReport
from zohra.core.enums import StrategyGroup, StrategyName
from zohra.indicators.mtf import calculate_mtf_alignment
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.mtf_alignment")


class MtfAlignmentStrategy(BaseStrategy):
    """
    Strategy 14: Enforces strict multi-timeframe alignment across M15 context bias,
    M5 market structure, and M1 entry timing.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.MTF_ALIGNMENT.value,
            strategy_group=StrategyGroup.TREND.value,
            allowed_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.BREAKOUT_EXPANSION
            ]
        )
        self.config = config or strategy_config.mtf_alignment

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < 30:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        mtf_data = calculate_mtf_alignment(df_m1=None, df_m5=df_entry, df_m15=df_htf)
        if not mtf_data.get("aligned", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        direction = mtf_data["direction"]

        # ─── MTF ALIGNMENT BUY ───
        if direction == "BUY" and regime_report.regime == MarketRegime.TRENDING_UP:
            recent_low = df_entry["low"].iloc[-5:].min()
            sl_price = round(recent_low - (0.3 * atr_val), 3)
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
                setup_quality=mtf_data.get("score", 90),
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Hierarchical MTF trend alignment (M15: {mtf_data['m15_bias']}, M5: {mtf_data['m5_bias']})",
                    f"MTF Confluence Score: {mtf_data['score']}/100",
                    f"Targeting trend continuation to {tp_price:.2f}"
                ],
                metadata={"mtf_score": mtf_data["score"], "m15_bias": mtf_data["m15_bias"]}
            )

        # ─── MTF ALIGNMENT SELL ───
        elif direction == "SELL" and regime_report.regime == MarketRegime.TRENDING_DOWN:
            recent_high = df_entry["high"].iloc[-5:].max()
            sl_price = round(recent_high + (0.3 * atr_val), 3)
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
                setup_quality=mtf_data.get("score", 90),
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Hierarchical MTF trend alignment (M15: {mtf_data['m15_bias']}, M5: {mtf_data['m5_bias']})",
                    f"MTF Confluence Score: {mtf_data['score']}/100",
                    f"Targeting trend continuation to {tp_price:.2f}"
                ],
                metadata={"mtf_score": mtf_data["score"], "m15_bias": mtf_data["m15_bias"]}
            )

        return None
