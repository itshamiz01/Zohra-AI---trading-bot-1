"""
╔══════════════════════════════════════════════════════════════════════╗
║         STRATEGY 4: OPENING RANGE / DONCHIAN BREAKOUT                ║
║           Volatility Expansion & Range Breakout Engine               ║
║              Group: BREAKOUT / VOLATILITY GROUP                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any, Tuple, Set
import pandas as pd
import numpy as np

from zohra.strategies.base_strategy import BaseStrategy, CandidateSignal
from zohra.core.market_regime import MarketRegime, RegimeReport
from zohra.core.enums import StrategyGroup, StrategyName
from zohra.indicators.atr import calculate_atr, calculate_relative_atr_expansion
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.breakout")


class BreakoutStrategy(BaseStrategy):
    """
    Strategy 4: Trades volatility expansions from defined consolidation ranges
    using both Opening Range Breakout (ORB) and Donchian Channels.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.BREAKOUT.value,
            strategy_group=StrategyGroup.BREAKOUT_VOLATILITY.value,
            allowed_regimes=[
                MarketRegime.BREAKOUT_EXPANSION,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN
            ]
        )
        self.config = config or strategy_config.breakout
        self.consumed_breakout_ids: Set[str] = set()

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < self.config.donchian_period + 5:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        atr_expansion = calculate_relative_atr_expansion(df_entry)
        if atr_expansion["expansion_ratio"] < self.config.min_atr_expansion_ratio:
            return None

        last_bar = df_entry.iloc[-1]
        prev_bar = df_entry.iloc[-2]

        close_p = float(last_bar["close"])
        high_p = float(last_bar["high"])
        low_p = float(last_bar["low"])
        open_p = float(last_bar["open"])

        ref_df = df_entry.iloc[-(self.config.donchian_period + 1):-1]
        donchian_high = float(ref_df["high"].max())
        donchian_low = float(ref_df["low"].min())

        candle_range = max(high_p - low_p, 1e-4)
        body_size = abs(close_p - open_p)
        is_strong_body = (body_size / candle_range) >= self.config.min_breakout_candle_body_ratio

        if not is_strong_body:
            return None

        candle_time = str(last_bar.get("timestamp", len(df_entry)))

        # ─── DONCHIAN LONG BREAKOUT ───
        if close_p > donchian_high and prev_bar["close"] <= donchian_high:
            breakout_id = f"DONCHIAN_LONG_{donchian_high:.2f}_{candle_time[:10]}"
            if breakout_id in self.consumed_breakout_ids:
                return None

            self.consumed_breakout_ids.add(breakout_id)
            sl_price = round(donchian_high - (1.2 * atr_val), 3)
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
                setup_quality=88,
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=95,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Donchian {self.config.donchian_period}-period High breakout above {donchian_high:.2f}",
                    f"Confirmed expansion body ({body_size/candle_range:.1%}) & ATR expansion ({atr_expansion['expansion_ratio']}x)",
                    f"Targeting momentum extension to {tp_price:.2f}"
                ],
                metadata={"donchian_high": donchian_high, "donchian_low": donchian_low, "breakout_id": breakout_id}
            )

        # ─── DONCHIAN SHORT BREAKOUT ───
        elif close_p < donchian_low and prev_bar["close"] >= donchian_low:
            breakout_id = f"DONCHIAN_SHORT_{donchian_low:.2f}_{candle_time[:10]}"
            if breakout_id in self.consumed_breakout_ids:
                return None

            self.consumed_breakout_ids.add(breakout_id)
            sl_price = round(donchian_low + (1.2 * atr_val), 3)
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
                setup_quality=88,
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=95,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Donchian {self.config.donchian_period}-period Low breakout below {donchian_low:.2f}",
                    f"Confirmed expansion body ({body_size/candle_range:.1%}) & ATR expansion ({atr_expansion['expansion_ratio']}x)",
                    f"Targeting momentum extension to {tp_price:.2f}"
                ],
                metadata={"donchian_high": donchian_high, "donchian_low": donchian_low, "breakout_id": breakout_id}
            )

        return None
