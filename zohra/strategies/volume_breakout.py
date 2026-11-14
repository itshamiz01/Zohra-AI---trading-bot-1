"""
╔══════════════════════════════════════════════════════════════════════╗
║           STRATEGY 11: VOLUME + BREAKOUT CONFIRMATION (XAUUSD)       ║
║            Range Breakout with Relative Tick Volume Surge            ║
║                 Group: BREAKOUT / VOLATILITY GROUP                   ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np

from zohra.strategies.base_strategy import BaseStrategy, CandidateSignal
from zohra.core.market_regime import MarketRegime, RegimeReport
from zohra.core.enums import StrategyGroup, StrategyName
from zohra.indicators.volume import check_volume_breakout
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.volume_breakout")


class VolumeBreakoutStrategy(BaseStrategy):
    """
    Strategy 11: Confirms high-probability range breakouts accompanied by
    significant Relative Volume (RVOL >= 1.35x 20-period tick volume).
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.VOLUME_BREAKOUT.value,
            strategy_group=StrategyGroup.BREAKOUT_VOLATILITY.value,
            allowed_regimes=[
                MarketRegime.BREAKOUT_EXPANSION,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.HIGH_VOLATILITY
            ]
        )
        self.config = config or strategy_config.volume_breakout

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < self.config.range_period + 5:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        vol_res = check_volume_breakout(df_entry, min_rvol=self.config.min_rvol)
        if not vol_res.get("volume_confirmed", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        direction = vol_res["direction"]
        breakout_lvl = vol_res["breakout_level"]
        rvol = vol_res["rvol"]

        # ─── VOLUME BREAKOUT BUY ───
        if direction == "BUY":
            sl_price = round(breakout_lvl - (1.2 * atr_val), 3)
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
                setup_quality=min(100, int(75 + (rvol * 15))),
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=95,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"20-period range breakout above {breakout_lvl:.2f}",
                    f"Relative Tick Volume surge confirmed (RVOL = {rvol}x > {self.config.min_rvol}x threshold)",
                    f"Targeting momentum continuation to {tp_price:.2f}"
                ],
                metadata={"rvol": rvol, "breakout_level": breakout_lvl}
            )

        # ─── VOLUME BREAKOUT SELL ───
        elif direction == "SELL":
            sl_price = round(breakout_lvl + (1.2 * atr_val), 3)
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
                setup_quality=min(100, int(75 + (rvol * 15))),
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=95,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"20-period range breakout below {breakout_lvl:.2f}",
                    f"Relative Tick Volume surge confirmed (RVOL = {rvol}x > {self.config.min_rvol}x threshold)",
                    f"Targeting momentum continuation to {tp_price:.2f}"
                ],
                metadata={"rvol": rvol, "breakout_level": breakout_lvl}
            )

        return None
