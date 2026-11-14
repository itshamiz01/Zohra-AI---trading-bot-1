"""
╔══════════════════════════════════════════════════════════════════════╗
║             STRATEGY 9: FAIR VALUE GAP RETRACEMENT (XAUUSD)          ║
║           3-Candle Imbalance Mitigation & Trend Continuation         ║
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
from zohra.indicators.fvg import check_fvg_retest
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.fvg")


class FvgRetracementStrategy(BaseStrategy):
    """
    Strategy 9: Detects 3-candle Fair Value Gaps (FVGs) and trades the retest/mitigation
    in alignment with dominant market structure.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.FVG_RETRACEMENT.value,
            strategy_group=StrategyGroup.STRUCTURE_SMC.value,
            allowed_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.BREAKOUT_EXPANSION,
                MarketRegime.RANGING,
                MarketRegime.ROTATIONAL
            ]
        )
        self.config = config or strategy_config.fvg

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

        fvg_data = check_fvg_retest(df_entry)
        if not fvg_data.get("retest", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        direction = fvg_data["direction"]
        fvg = fvg_data.get("fvg", {})

        # ─── BULLISH FVG RETEST BUY ───
        if direction == "BUY":
            fvg_bottom = fvg_data["fvg_bottom"]
            sl_price = round(fvg_bottom - (0.3 * atr_val), 3)
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
                    f"Bullish Fair Value Gap retest ({fvg_data['fvg_bottom']:.2f} - {fvg_data['fvg_top']:.2f})",
                    f"Imbalance gap size: {fvg.get('gap_size', 0):.2f} ({fvg.get('gap_atr_ratio', 0)}x ATR)",
                    f"Mitigation reaction confirmed, targeting +{self.config.min_risk_reward}R expansion"
                ],
                metadata={"fvg_top": fvg_data["fvg_top"], "fvg_bottom": fvg_bottom}
            )

        # ─── BEARISH FVG RETEST SELL ───
        elif direction == "SELL":
            fvg_top = fvg_data["fvg_top"]
            sl_price = round(fvg_top + (0.3 * atr_val), 3)
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
                    f"Bearish Fair Value Gap retest ({fvg_data['fvg_bottom']:.2f} - {fvg_data['fvg_top']:.2f})",
                    f"Imbalance gap size: {fvg.get('gap_size', 0):.2f} ({fvg.get('gap_atr_ratio', 0)}x ATR)",
                    f"Mitigation reaction confirmed, targeting -{self.config.min_risk_reward}R expansion"
                ],
                metadata={"fvg_top": fvg_top, "fvg_bottom": fvg_data["fvg_bottom"]}
            )

        return None
