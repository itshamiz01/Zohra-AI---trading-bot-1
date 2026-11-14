"""
╔══════════════════════════════════════════════════════════════════════╗
║         STRATEGY 15: FALSE BREAKOUT / BREAKOUT FAILURE (XAUUSD)      ║
║            Trapped Liquidity & Failed Breakout Reversal Engine       ║
║                  Group: STRUCTURE / SMC GROUP                        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np

from zohra.strategies.base_strategy import BaseStrategy, CandidateSignal
from zohra.core.market_regime import MarketRegime, RegimeReport
from zohra.core.enums import StrategyGroup, StrategyName
from zohra.indicators.market_structure import find_swing_points
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.false_breakout")


class FalseBreakoutStrategy(BaseStrategy):
    """
    Strategy 15: Identifies trapped breakout traders beyond major support/resistance levels
    where price breaks out, fails to hold follow-through, and swiftly reclaims back inside.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.FALSE_BREAKOUT.value,
            strategy_group=StrategyGroup.STRUCTURE_SMC.value,
            allowed_regimes=[
                MarketRegime.RANGING,
                MarketRegime.ROTATIONAL,
                MarketRegime.HIGH_VOLATILITY,
                MarketRegime.UNCLEAR,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN
            ]
        )
        self.config = config or strategy_config.false_breakout

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

        ref_df = df_entry.iloc[-25:-3]
        recent_bars = df_entry.iloc[-3:]

        ref_high = float(ref_df["high"].max())
        ref_low = float(ref_df["low"].min())

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        high_3 = float(recent_bars["high"].max())
        low_3 = float(recent_bars["low"].min())

        # ─── FALSE UPSIDE BREAKOUT (BULL TRAP -> SELL) ───
        if high_3 > ref_high and close_p < ref_high:
            trap_extreme = high_3
            reclaim_dist = ref_high - close_p
            if reclaim_dist >= (0.2 * atr_val):
                sl_price = round(trap_extreme + (0.3 * atr_val), 3)
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
                    setup_quality=90,
                    confidence=regime_report.confidence,
                    regime_match_score=95,
                    volatility_score=90,
                    spread_score=90 if current_spread_pips <= 2.5 else 70,
                    reasons=[
                        f"False upside breakout (Bull Trap) above resistance {ref_high:.2f} (Extreme: {trap_extreme:.2f})",
                        f"Price failed follow-through and reclaimed inside range (-{reclaim_dist:.2f} USD)",
                        f"Targeting opposing range expansion to {tp_price:.2f}"
                    ],
                    metadata={"failed_level": ref_high, "trap_extreme": trap_extreme}
                )

        # ─── FALSE DOWNSIDE BREAKOUT (BEAR TRAP -> BUY) ───
        elif low_3 < ref_low and close_p > ref_low:
            trap_extreme = low_3
            reclaim_dist = close_p - ref_low
            if reclaim_dist >= (0.2 * atr_val):
                sl_price = round(trap_extreme - (0.3 * atr_val), 3)
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
                    setup_quality=90,
                    confidence=regime_report.confidence,
                    regime_match_score=95,
                    volatility_score=90,
                    spread_score=90 if current_spread_pips <= 2.5 else 70,
                    reasons=[
                        f"False downside breakout (Bear Trap) below support {ref_low:.2f} (Extreme: {trap_extreme:.2f})",
                        f"Price failed follow-through and reclaimed inside range (+{reclaim_dist:.2f} USD)",
                        f"Targeting opposing range expansion to {tp_price:.2f}"
                    ],
                    metadata={"failed_level": ref_low, "trap_extreme": trap_extreme}
                )

        return None
