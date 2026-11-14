"""
╔══════════════════════════════════════════════════════════════════════╗
║        STRATEGY 3: LIQUIDITY SWEEP + MARKET STRUCTURE SHIFT          ║
║         Institutional Stop-Hunt False Breakout Reversal Engine       ║
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
from zohra.indicators.market_structure import (
    detect_liquidity_sweep,
    detect_market_structure_shift,
    find_swing_points
)
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.liquidity_mss")


class LiquidityMssStrategy(BaseStrategy):
    """
    Strategy 3: Identifies false breakouts (liquidity sweeps) beyond key swing highs/lows
    and enters only upon a confirmed Market Structure Shift (MSS / CHOCH).
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.LIQUIDITY_MSS.value,
            strategy_group=StrategyGroup.STRUCTURE_SMC.value,
            allowed_regimes=[
                MarketRegime.RANGING,
                MarketRegime.ROTATIONAL,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.HIGH_VOLATILITY
            ]
        )
        self.config = config or strategy_config.liquidity_mss

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

        sweep_info = detect_liquidity_sweep(df_entry, lookback_bars=self.config.sweep_lookback_bars)
        if not sweep_info.get("swept", False):
            return None

        mss_info = detect_market_structure_shift(df_entry, sweep_info)
        if not mss_info.get("mss_confirmed", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        direction = mss_info.get("direction")

        # ─── BULLISH REVERSAL SETUP ───
        if direction == "LONG":
            sweep_low = sweep_info["sweep_extreme"]
            buffer = self.config.stop_buffer_pips * 0.10
            sl_price = round(sweep_low - buffer - (0.2 * atr_val), 3)

            stop_dist = max(close_p - sl_price, 0.8 * atr_val)
            swing_highs, _ = find_swing_points(df_entry.iloc[-30:], left_bars=2, right_bars=2)
            target_high = max(s["price"] for s in swing_highs) if swing_highs else close_p + (stop_dist * self.config.min_risk_reward)
            reward_dist = max(target_high - close_p, stop_dist * self.config.min_risk_reward)
            tp_price = round(close_p + reward_dist, 3)
            rr = reward_dist / stop_dist

            return CandidateSignal(
                strategy_name=self.name,
                strategy_group=self.strategy_group,
                symbol=strategy_config.gold_symbol,
                direction="BUY",
                entry_price=round(close_p, 3),
                stop_loss=sl_price,
                take_profit=tp_price,
                risk_reward=round(rr, 2),
                stop_distance_pips=round(stop_dist * 10.0, 1),
                setup_quality=92,
                confidence=min(95, regime_report.confidence + 10),
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"SSL Liquidity Sweep below {sweep_info['level']:.2f} (Extreme: {sweep_low:.2f})",
                    f"Confirmed BULLISH_MSS break above {mss_info['breakout_level']:.2f}",
                    f"Targeting opposing Buy-Side Liquidity at {tp_price:.2f}"
                ],
                metadata={"sweep": sweep_info, "mss": mss_info}
            )

        # ─── BEARISH REVERSAL SETUP ───
        elif direction == "SHORT":
            sweep_high = sweep_info["sweep_extreme"]
            buffer = self.config.stop_buffer_pips * 0.10
            sl_price = round(sweep_high + buffer + (0.2 * atr_val), 3)

            stop_dist = max(sl_price - close_p, 0.8 * atr_val)
            _, swing_lows = find_swing_points(df_entry.iloc[-30:], left_bars=2, right_bars=2)
            target_low = min(s["price"] for s in swing_lows) if swing_lows else close_p - (stop_dist * self.config.min_risk_reward)
            reward_dist = max(close_p - target_low, stop_dist * self.config.min_risk_reward)
            tp_price = round(close_p - reward_dist, 3)
            rr = reward_dist / stop_dist

            return CandidateSignal(
                strategy_name=self.name,
                strategy_group=self.strategy_group,
                symbol=strategy_config.gold_symbol,
                direction="SELL",
                entry_price=round(close_p, 3),
                stop_loss=sl_price,
                take_profit=tp_price,
                risk_reward=round(rr, 2),
                stop_distance_pips=round(stop_dist * 10.0, 1),
                setup_quality=92,
                confidence=min(95, regime_report.confidence + 10),
                regime_match_score=95,
                volatility_score=90,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"BSL Liquidity Sweep above {sweep_info['level']:.2f} (Extreme: {sweep_high:.2f})",
                    f"Confirmed BEARISH_MSS break below {mss_info['breakout_level']:.2f}",
                    f"Targeting opposing Sell-Side Liquidity at {tp_price:.2f}"
                ],
                metadata={"sweep": sweep_info, "mss": mss_info}
            )

        return None
