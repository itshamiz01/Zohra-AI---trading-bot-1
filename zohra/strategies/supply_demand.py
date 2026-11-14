"""
╔══════════════════════════════════════════════════════════════════════╗
║              STRATEGY 8: SUPPLY & DEMAND ZONE (XAUUSD)               ║
║           Institutional Imbalance Reaction & Return Engine           ║
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
from zohra.indicators.supply_demand import check_supply_demand_reaction
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.supply_demand")


class SupplyDemandStrategy(BaseStrategy):
    """
    Strategy 8: Identifies institutional displacement zones (Supply & Demand bases)
    and enters on fresh/tested mitigation returns with confirmed candle rejection.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.SUPPLY_DEMAND.value,
            strategy_group=StrategyGroup.STRUCTURE_SMC.value,
            allowed_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.RANGING,
                MarketRegime.ROTATIONAL,
                MarketRegime.HIGH_VOLATILITY,
                MarketRegime.BREAKOUT_EXPANSION
            ]
        )
        self.config = config or strategy_config.supply_demand

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < 35:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        reaction = check_supply_demand_reaction(df_entry)
        if not reaction.get("in_zone", False):
            return None

        zone = reaction.get("zone", {})
        if self.config.require_fresh and zone.get("status") != "FRESH":
            return None

        if zone.get("touches", 0) > self.config.max_touch_count:
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        direction = reaction["direction"]

        # ─── DEMAND ZONE REACTION BUY ───
        if direction == "BUY":
            zone_low = reaction["zone_low"]
            sl_price = round(zone_low - (0.3 * atr_val), 3)
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
                setup_quality=zone.get("strength", 85),
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Institutional Demand Zone reaction at {reaction['zone_high']:.2f} - {zone_low:.2f}",
                    f"Zone status: {zone.get('status')} (Touches: {zone.get('touches')}, Strength: {zone.get('strength')}/100)",
                    f"Bullish rejection confirmed, targeting {tp_price:.2f}"
                ],
                metadata={"zone_id": zone.get("zone_id"), "zone_high": reaction["zone_high"], "zone_low": zone_low}
            )

        # ─── SUPPLY ZONE REACTION SELL ───
        elif direction == "SELL":
            zone_high = reaction["zone_high"]
            sl_price = round(zone_high + (0.3 * atr_val), 3)
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
                setup_quality=zone.get("strength", 85),
                confidence=regime_report.confidence,
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Institutional Supply Zone reaction at {zone_high:.2f} - {reaction['zone_low']:.2f}",
                    f"Zone status: {zone.get('status')} (Touches: {zone.get('touches')}, Strength: {zone.get('strength')}/100)",
                    f"Bearish rejection confirmed, targeting {tp_price:.2f}"
                ],
                metadata={"zone_id": zone.get("zone_id"), "zone_high": zone_high, "zone_low": reaction["zone_low"]}
            )

        return None
