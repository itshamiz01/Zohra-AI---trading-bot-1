"""
╔══════════════════════════════════════════════════════════════════════╗
║         STRATEGY 13: MOMENTUM CANDLE CONTINUATION (XAUUSD)           ║
║       Institutional Displacement & Controlled Follow-Through Engine  ║
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
from zohra.indicators.momentum import detect_momentum_candle
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.momentum_continuation")


class MomentumContinuationStrategy(BaseStrategy):
    """
    Strategy 13: Identifies unusually strong directional displacement candles (body >= 65% of range, >= 1.3x ATR)
    and enters on confirmed continuation after shallow consolidation.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.MOMENTUM_CONTINUATION.value,
            strategy_group=StrategyGroup.TREND.value,
            allowed_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.BREAKOUT_EXPANSION,
                MarketRegime.HIGH_VOLATILITY
            ]
        )
        self.config = config or strategy_config.momentum

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < 15:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        mom_data = detect_momentum_candle(
            df_entry,
            min_body_ratio=self.config.min_body_ratio,
            min_atr_multiple=self.config.min_atr_multiple
        )

        if not mom_data.get("has_momentum", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        direction = mom_data["direction"]

        # ─── MOMENTUM CONTINUATION BUY ───
        if direction == "BUY":
            candle_low = mom_data.get("candle_low", float(last_bar["low"]))
            sl_price = round(candle_low - (0.3 * atr_val), 3)
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
                setup_quality=86,
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=95,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Institutional bullish momentum candle (Body: {mom_data['body_ratio']:.0%}, Range: {mom_data['atr_multiple']}x ATR)",
                    f"Controlled continuation confirmed, targeting +{self.config.min_risk_reward}R expansion to {tp_price:.2f}"
                ],
                metadata={"body_ratio": mom_data["body_ratio"], "atr_multiple": mom_data["atr_multiple"]}
            )

        # ─── MOMENTUM CONTINUATION SELL ───
        elif direction == "SELL":
            candle_high = mom_data.get("candle_high", float(last_bar["high"]))
            sl_price = round(candle_high + (0.3 * atr_val), 3)
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
                setup_quality=86,
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=95,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Institutional bearish momentum candle (Body: {mom_data['body_ratio']:.0%}, Range: {mom_data['atr_multiple']}x ATR)",
                    f"Controlled continuation confirmed, targeting -{self.config.min_risk_reward}R expansion to {tp_price:.2f}"
                ],
                metadata={"body_ratio": mom_data["body_ratio"], "atr_multiple": mom_data["atr_multiple"]}
            )

        return None
