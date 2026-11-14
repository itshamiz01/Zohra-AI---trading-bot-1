"""
╔══════════════════════════════════════════════════════════════════════╗
║              STRATEGY 10: ORDER BLOCK RETEST (XAUUSD)                ║
║         Institutional Footprint Mitigation & Reversal Scalper        ║
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
from zohra.indicators.order_block import check_order_block_retest
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.order_block")


class OrderBlockStrategy(BaseStrategy):
    """
    Strategy 10: Trades the retest and mitigation of high-probability institutional Order Blocks
    (last opposing candle before structural market displacement).
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.ORDER_BLOCK.value,
            strategy_group=StrategyGroup.STRUCTURE_SMC.value,
            allowed_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.BREAKOUT_EXPANSION,
                MarketRegime.RANGING,
                MarketRegime.ROTATIONAL
            ]
        )
        self.config = config or strategy_config.order_block

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

        ob_data = check_order_block_retest(df_entry)
        if not ob_data.get("retest", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        direction = ob_data["direction"]
        ob = ob_data.get("ob", {})

        # ─── BULLISH OB RETEST BUY ───
        if direction == "BUY":
            ob_low = ob_data["ob_low"]
            sl_price = round(ob_low - (0.3 * atr_val), 3)
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
                setup_quality=92,
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Bullish Order Block retest ({ob_data['ob_low']:.2f} - {ob_data['ob_high']:.2f})",
                    f"Displacement strength: {ob.get('displacement', 0):.2f} ({ob.get('displacement', 0)/atr_val:.1f}x ATR)",
                    f"Mitigation reaction confirmed, targeting +{self.config.min_risk_reward}R expansion"
                ],
                metadata={"ob_high": ob_data["ob_high"], "ob_low": ob_low}
            )

        # ─── BEARISH OB RETEST SELL ───
        elif direction == "SELL":
            ob_high = ob_data["ob_high"]
            sl_price = round(ob_high + (0.3 * atr_val), 3)
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
                setup_quality=92,
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Bearish Order Block retest ({ob_data['ob_low']:.2f} - {ob_data['ob_high']:.2f})",
                    f"Displacement strength: {ob.get('displacement', 0):.2f} ({ob.get('displacement', 0)/atr_val:.1f}x ATR)",
                    f"Mitigation reaction confirmed, targeting -{self.config.min_risk_reward}R expansion"
                ],
                metadata={"ob_high": ob_high, "ob_low": ob_data["ob_low"]}
            )

        return None
