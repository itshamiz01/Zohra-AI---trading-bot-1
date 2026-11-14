"""
╔══════════════════════════════════════════════════════════════════════╗
║        STRATEGY 5: BOLLINGER BANDS + RSI REVERSAL (XAUUSD)           ║
║         Statistical Exhaustion & Mean Reversion in Range Markets     ║
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
from zohra.indicators.bollinger import calculate_bollinger_bands
from zohra.indicators.rsi import calculate_rsi
from zohra.indicators.atr import calculate_atr
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.bollinger_rsi")


class BollingerRsiStrategy(BaseStrategy):
    """
    Strategy 5: Trades statistical price exhaustion when price pierces
    Bollinger Bands with extreme RSI, strictly in non-trending markets.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.BOLLINGER_RSI.value,
            strategy_group=StrategyGroup.MEAN_REVERSION.value,
            allowed_regimes=[
                MarketRegime.RANGING,
                MarketRegime.ROTATIONAL,
                MarketRegime.HIGH_VOLATILITY,
                MarketRegime.UNCLEAR
            ]
        )
        self.config = config or strategy_config.bollinger_rsi

    def evaluate(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                 regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Optional[CandidateSignal]:
        if not self.config.enabled:
            return None

        is_eligible, reason = self.is_eligible(regime_report)
        if not is_eligible:
            return None

        if regime_report.adx_value >= self.config.max_adx_trend:
            return None

        if df_entry is None or len(df_entry) < max(self.config.bb_period, self.config.rsi_period) + 5:
            return None

        atr_val = calculate_atr(df_entry, period=14)
        if atr_val <= 0:
            atr_val = 1.0

        bb_data = calculate_bollinger_bands(df_entry, self.config.bb_period, self.config.bb_std_dev)
        rsi_series = calculate_rsi(df_entry, self.config.rsi_period)
        rsi_val = float(rsi_series.iloc[-1]) if isinstance(rsi_series, pd.Series) and not rsi_series.empty and not np.isnan(rsi_series.iloc[-1]) else 50.0

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        open_p = float(last_bar["open"])

        upper_bb = float(bb_data["upper"].iloc[-1])
        lower_bb = float(bb_data["lower"].iloc[-1])
        middle_bb = float(bb_data["middle"].iloc[-1])

        # ─── OVERSOLD BOLLINGER + RSI BUY ───
        recent_low = df_entry["low"].iloc[-3:].min()
        pierced_lower = recent_low <= lower_bb
        rsi_oversold = rsi_val <= self.config.rsi_oversold or df_entry["low"].iloc[-2] <= lower_bb
        is_bullish_close = close_p > open_p and close_p > lower_bb

        if pierced_lower and rsi_oversold and is_bullish_close:
            sl_price = round(recent_low - (0.4 * atr_val), 3)
            stop_dist = max(close_p - sl_price, 0.6 * atr_val)

            reward_dist = middle_bb - close_p
            if reward_dist < (stop_dist * self.config.min_risk_reward):
                reward_dist = stop_dist * self.config.min_risk_reward

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
                setup_quality=84,
                confidence=regime_report.confidence,
                regime_match_score=90,
                volatility_score=80,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Lower Bollinger Band penetration ({recent_low:.2f} <= {lower_bb:.2f})",
                    f"RSI Oversold ({rsi_val:.1f} <= {self.config.rsi_oversold}) in {regime_report.regime.value}",
                    f"Bullish reclaim close inside band, targeting 20 SMA ({middle_bb:.2f})"
                ],
                metadata={"rsi": rsi_val, "lower_bb": lower_bb, "middle_bb": middle_bb}
            )

        # ─── OVERBOUGHT BOLLINGER + RSI SELL ───
        recent_high = df_entry["high"].iloc[-3:].max()
        pierced_upper = recent_high >= upper_bb
        rsi_overbought = rsi_val >= self.config.rsi_overbought or df_entry["high"].iloc[-2] >= upper_bb
        is_bearish_close = close_p < open_p and close_p < upper_bb

        if pierced_upper and rsi_overbought and is_bearish_close:
            sl_price = round(recent_high + (0.4 * atr_val), 3)
            stop_dist = max(sl_price - close_p, 0.6 * atr_val)

            reward_dist = close_p - middle_bb
            if reward_dist < (stop_dist * self.config.min_risk_reward):
                reward_dist = stop_dist * self.config.min_risk_reward

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
                setup_quality=84,
                confidence=regime_report.confidence,
                regime_match_score=90,
                volatility_score=80,
                spread_score=90 if current_spread_pips <= 2.5 else 70,
                reasons=[
                    f"Upper Bollinger Band penetration ({recent_high:.2f} >= {upper_bb:.2f})",
                    f"RSI Overbought ({rsi_val:.1f} >= {self.config.rsi_overbought}) in {regime_report.regime.value}",
                    f"Bearish reclaim close inside band, targeting 20 SMA ({middle_bb:.2f})"
                ],
                metadata={"rsi": rsi_val, "upper_bb": upper_bb, "middle_bb": middle_bb}
            )

        return None
