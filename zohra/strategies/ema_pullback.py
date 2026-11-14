"""
╔══════════════════════════════════════════════════════════════════════╗
║               STRATEGY 1: EMA PULLBACK TREND (XAUUSD)                ║
║           Trend Continuation After Controlled Counter-Dips           ║
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
from zohra.indicators.ema import check_ema_alignment
from zohra.indicators.atr import calculate_atr
from zohra.indicators.market_structure import find_swing_points
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.ema_pullback")


class EmaPullbackStrategy(BaseStrategy):
    """
    Strategy 1: Joins established trends after price temporarily pulls back
    into the EMA 9/21 dynamic value zone and prints a confirmed rejection.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.EMA_PULLBACK.value,
            strategy_group=StrategyGroup.TREND.value,
            allowed_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]
        )
        self.config = config or strategy_config.ema_pullback

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if df_entry is None or len(df_entry) < 35:
            return None

        entry_ema = check_ema_alignment(df_entry, self.config.fast_ema_period, self.config.slow_ema_period, self.config.trend_ema_period)
        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        high_p = float(last_bar["high"])
        low_p = float(last_bar["low"])
        open_p = float(last_bar["open"])

        fast_ema = entry_ema["fast_ema"]
        slow_ema = entry_ema["slow_ema"]
        trend_ema = entry_ema["trend_ema"]
        ema_high = max(fast_ema, slow_ema)
        ema_low = min(fast_ema, slow_ema)

        htf_bullish = True
        htf_bearish = True
        if df_htf is not None and len(df_htf) >= 30:
            htf_ema = check_ema_alignment(df_htf, self.config.fast_ema_period, self.config.slow_ema_period, self.config.trend_ema_period)
            htf_bullish = htf_ema["bullish"]
            htf_bearish = htf_ema["bearish"]

        # ─── LONG SETUP ───
        if regime_report.regime == MarketRegime.TRENDING_UP and htf_bullish and entry_ema["bullish"]:
            recent_lows = df_entry["low"].iloc[-3:].min()
            in_pullback_zone = recent_lows <= (ema_high + (0.3 * atr_val)) and recent_lows >= (trend_ema - (0.5 * atr_val))

            candle_range = max(high_p - low_p, 1e-4)
            lower_wick = min(open_p, close_p) - low_p
            is_bullish_rejection = (lower_wick / candle_range >= 0.35) or (close_p > open_p and close_p > fast_ema)

            if in_pullback_zone and is_bullish_rejection:
                swing_highs, swing_lows = find_swing_points(df_entry.iloc[-20:], left_bars=2, right_bars=2)
                sl_price = min(s["price"] for s in swing_lows[-2:]) - (0.2 * atr_val) if swing_lows else low_p - (1.2 * atr_val)
                stop_dist = max(close_p - sl_price, 0.8 * atr_val)
                sl_price = round(close_p - stop_dist, 3)
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
                    setup_quality=85,
                    confidence=regime_report.confidence,
                    regime_match_score=95,
                    volatility_score=85,
                    spread_score=90 if current_spread_pips <= 2.5 else 70,
                    reasons=[
                        f"Trend UP alignment (HTF & Entry)",
                        f"Pullback into EMA {self.config.fast_ema_period}/{self.config.slow_ema_period} zone",
                        f"Bullish rejection confirmed (Close={close_p:.2f} > Fast EMA={fast_ema:.2f})"
                    ],
                    metadata={"fast_ema": fast_ema, "slow_ema": slow_ema, "atr": atr_val}
                )

        # ─── SHORT SETUP ───
        elif regime_report.regime == MarketRegime.TRENDING_DOWN and htf_bearish and entry_ema["bearish"]:
            recent_highs = df_entry["high"].iloc[-3:].max()
            in_pullback_zone = recent_highs >= (ema_low - (0.3 * atr_val)) and recent_highs <= (trend_ema + (0.5 * atr_val))

            candle_range = max(high_p - low_p, 1e-4)
            upper_wick = high_p - max(open_p, close_p)
            is_bearish_rejection = (upper_wick / candle_range >= 0.35) or (close_p < open_p and close_p < fast_ema)

            if in_pullback_zone and is_bearish_rejection:
                swing_highs, swing_lows = find_swing_points(df_entry.iloc[-20:], left_bars=2, right_bars=2)
                sl_price = max(s["price"] for s in swing_highs[-2:]) + (0.2 * atr_val) if swing_highs else high_p + (1.2 * atr_val)
                stop_dist = max(sl_price - close_p, 0.8 * atr_val)
                sl_price = round(close_p + stop_dist, 3)
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
                    setup_quality=85,
                    confidence=regime_report.confidence,
                    regime_match_score=95,
                    volatility_score=85,
                    spread_score=90 if current_spread_pips <= 2.5 else 70,
                    reasons=[
                        f"Trend DOWN alignment (HTF & Entry)",
                        f"Pullback into EMA {self.config.fast_ema_period}/{self.config.slow_ema_period} zone",
                        f"Bearish rejection confirmed (Close={close_p:.2f} < Fast EMA={fast_ema:.2f})"
                    ],
                    metadata={"fast_ema": fast_ema, "slow_ema": slow_ema, "atr": atr_val}
                )

        return None
