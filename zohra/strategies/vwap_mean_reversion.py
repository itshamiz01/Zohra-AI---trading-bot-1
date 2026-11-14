"""
╔══════════════════════════════════════════════════════════════════════╗
║             STRATEGY 2: VWAP MEAN REVERSION (XAUUSD)                 ║
║      Value Anchor Mean Reversion in Ranging/Rotational Markets       ║
║                 Group: MEAN_REVERSION GROUP                          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np

from zohra.strategies.base_strategy import BaseStrategy, CandidateSignal
from zohra.core.market_regime import MarketRegime, RegimeReport
from zohra.core.enums import StrategyGroup, StrategyName
from zohra.indicators.vwap import calculate_vwap, calculate_vwap_distance_atr
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.vwap_mean_reversion")


class VwapMeanReversionStrategy(BaseStrategy):
    """
    Strategy 2: Fades statistical overextensions away from session VWAP
    strictly during non-trending (RANGING or ROTATIONAL) regimes.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.VWAP_MEAN_REVERSION.value,
            strategy_group=StrategyGroup.MEAN_REVERSION.value,
            allowed_regimes=[MarketRegime.RANGING, MarketRegime.ROTATIONAL]
        )
        self.config = config or strategy_config.vwap_reversion

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if regime_report.adx_value >= self.config.max_adx_trend:
            return None

        if df_entry is None or len(df_entry) < 30:
            return None

        vwap_series = calculate_vwap(df_entry)
        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        high_p = float(last_bar["high"])
        low_p = float(last_bar["low"])
        open_p = float(last_bar["open"])
        vwap_val = float(vwap_series.iloc[-1])

        dist_atr = calculate_vwap_distance_atr(close_p, vwap_val, atr_val)
        candle_range = max(high_p - low_p, 1e-4)

        # ─── LONG SETUP (Oversold below VWAP) ───
        if dist_atr <= -self.config.min_stretch_atr:
            lower_wick = min(open_p, close_p) - low_p
            is_bullish_rejection = (lower_wick / candle_range >= self.config.min_rejection_wick_ratio) or (close_p > open_p)

            if is_bullish_rejection:
                tp_price = round(close_p + (abs(vwap_val - close_p) * 0.85), 3)
                recent_low = df_entry["low"].iloc[-5:].min()
                sl_price = round(recent_low - (0.3 * atr_val), 3)

                stop_dist = max(close_p - sl_price, 0.6 * atr_val)
                reward_dist = max(tp_price - close_p, 0.1)
                rr = reward_dist / stop_dist

                if rr >= self.config.min_risk_reward:
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
                        setup_quality=85,
                        confidence=regime_report.confidence,
                        regime_match_score=90,
                        volatility_score=80,
                        spread_score=90 if current_spread_pips <= 2.5 else 70,
                        reasons=[
                            f"Price stretched {abs(dist_atr):.1f}x ATR below VWAP in {regime_report.regime.value}",
                            f"Bullish rejection wick confirmed",
                            f"Targeting return to VWAP ({vwap_val:.2f})"
                        ],
                        metadata={"vwap": vwap_val, "dist_atr": dist_atr, "atr": atr_val}
                    )

        # ─── SHORT SETUP (Overbought above VWAP) ───
        elif dist_atr >= self.config.min_stretch_atr:
            upper_wick = high_p - max(open_p, close_p)
            is_bearish_rejection = (upper_wick / candle_range >= self.config.min_rejection_wick_ratio) or (close_p < open_p)

            if is_bearish_rejection:
                tp_price = round(close_p - (abs(close_p - vwap_val) * 0.85), 3)
                recent_high = df_entry["high"].iloc[-5:].max()
                sl_price = round(recent_high + (0.3 * atr_val), 3)

                stop_dist = max(sl_price - close_p, 0.6 * atr_val)
                reward_dist = max(close_p - tp_price, 0.1)
                rr = reward_dist / stop_dist

                if rr >= self.config.min_risk_reward:
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
                        setup_quality=85,
                        confidence=regime_report.confidence,
                        regime_match_score=90,
                        volatility_score=80,
                        spread_score=90 if current_spread_pips <= 2.5 else 70,
                        reasons=[
                            f"Price stretched {dist_atr:.1f}x ATR above VWAP in {regime_report.regime.value}",
                            f"Bearish rejection wick confirmed",
                            f"Targeting return to VWAP ({vwap_val:.2f})"
                        ],
                        metadata={"vwap": vwap_val, "dist_atr": dist_atr, "atr": atr_val}
                    )

        return None
