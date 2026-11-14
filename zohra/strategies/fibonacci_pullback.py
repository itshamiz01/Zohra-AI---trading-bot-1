"""
╔══════════════════════════════════════════════════════════════════════╗
║              STRATEGY 6: FIBONACCI PULLBACK (XAUUSD)                 ║
║         Golden Pocket (38.2% - 61.8%) Impulsive Retracement Engine   ║
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
from zohra.indicators.fibonacci import detect_fibonacci_retracement
from zohra.indicators.atr import calculate_atr
from zohra.indicators.ema import check_ema_alignment
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.fibonacci_pullback")


class FibonacciPullbackStrategy(BaseStrategy):
    """
    Strategy 6: Trades deep retracements inside an established directional trend
    specifically targeting the 38.2%, 50.0%, and 61.8% Golden Pocket with structure rejection.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.FIBONACCI_PULLBACK.value,
            strategy_group=StrategyGroup.TREND.value,
            allowed_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]
        )
        self.config = config or strategy_config.fibonacci_pullback

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < self.config.swing_lookback:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        is_uptrend = (regime_report.regime == MarketRegime.TRENDING_UP)
        fib_data = detect_fibonacci_retracement(df_entry, is_uptrend=is_uptrend, lookback=self.config.swing_lookback)

        if not fib_data.get("in_zone", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        high_p = float(last_bar["high"])
        low_p = float(last_bar["low"])
        open_p = float(last_bar["open"])
        candle_range = max(high_p - low_p, 1e-4)

        # ─── BULLISH FIBONACCI RETRACEMENT BUY ───
        if is_uptrend:
            lower_wick = min(open_p, close_p) - low_p
            is_bullish_rejection = (lower_wick / candle_range >= 0.30) or (close_p > open_p)

            if is_bullish_rejection:
                impulse_low = fib_data["impulse_low"]
                sl_price = round(impulse_low - (0.3 * atr_val), 3)
                stop_dist = max(close_p - sl_price, 0.8 * atr_val)

                impulse_high = fib_data["impulse_high"]
                reward_dist = max(impulse_high - close_p, stop_dist * self.config.min_risk_reward)
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
                    setup_quality=88,
                    confidence=regime_report.confidence,
                    regime_match_score=95,
                    volatility_score=85,
                    spread_score=90 if current_spread_pips <= 2.5 else 70,
                    reasons=[
                        f"Price retraced into Fibonacci {fib_data['zone']} (Impulse: {impulse_low:.2f} -> {impulse_high:.2f})",
                        f"Bullish rejection wick confirmed at {fib_data['nearest_level']:.2f}",
                        f"Targeting previous impulse high at {impulse_high:.2f}"
                    ],
                    metadata={"fib_levels": fib_data.get("levels"), "nearest_level": fib_data["nearest_level"]}
                )

        # ─── BEARISH FIBONACCI RETRACEMENT SELL ───
        else:
            upper_wick = high_p - max(open_p, close_p)
            is_bearish_rejection = (upper_wick / candle_range >= 0.30) or (close_p < open_p)

            if is_bearish_rejection:
                impulse_high = fib_data["impulse_high"]
                sl_price = round(impulse_high + (0.3 * atr_val), 3)
                stop_dist = max(sl_price - close_p, 0.8 * atr_val)

                impulse_low = fib_data["impulse_low"]
                reward_dist = max(close_p - impulse_low, stop_dist * self.config.min_risk_reward)
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
                    setup_quality=88,
                    confidence=regime_report.confidence,
                    regime_match_score=95,
                    volatility_score=85,
                    spread_score=90 if current_spread_pips <= 2.5 else 70,
                    reasons=[
                        f"Price retraced into Fibonacci {fib_data['zone']} (Impulse: {impulse_high:.2f} -> {impulse_low:.2f})",
                        f"Bearish rejection wick confirmed at {fib_data['nearest_level']:.2f}",
                        f"Targeting previous impulse low at {impulse_low:.2f}"
                    ],
                    metadata={"fib_levels": fib_data.get("levels"), "nearest_level": fib_data["nearest_level"]}
                )

        return None
