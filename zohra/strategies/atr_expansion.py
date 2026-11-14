"""
╔══════════════════════════════════════════════════════════════════════╗
║         STRATEGY 12: ATR COMPRESSION → EXPANSION (XAUUSD)            ║
║        Volatility Cycle Transition & Expansion Breakout Engine       ║
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
from zohra.indicators.atr import calculate_atr, detect_atr_compression_expansion
from zohra.indicators.ema import check_ema_alignment
from zohra.config.strategy_config import strategy_config

logger = logging.getLogger("zohra.strategy.atr_expansion")


class AtrExpansionStrategy(BaseStrategy):
    """
    Strategy 12: Detects volatility cycle transition: extended multi-candle ATR contraction/compression
    followed by an explosive expansion breakout in the direction of local trend/momentum.
    """

    def __init__(self, config=None):
        super().__init__(
            name=StrategyName.ATR_EXPANSION.value,
            strategy_group=StrategyGroup.BREAKOUT_VOLATILITY.value,
            allowed_regimes=[
                MarketRegime.BREAKOUT_EXPANSION,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.HIGH_VOLATILITY
            ]
        )
        self.config = config or strategy_config.atr_expansion

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

        comp_data = detect_atr_compression_expansion(df_entry, compression_bars=self.config.compression_bars)
        if not comp_data.get("compression_breakout", False):
            return None

        last_bar = df_entry.iloc[-1]
        close_p = float(last_bar["close"])
        open_p = float(last_bar["open"])

        ema_data = check_ema_alignment(df_entry, fast=9, slow=21, trend=50)

        # ─── ATR EXPANSION BUY ───
        if close_p > open_p and (ema_data["bullish"] or regime_report.regime == MarketRegime.TRENDING_UP or ema_data["fast_slope"] > 0):
            recent_low = df_entry["low"].iloc[-5:].min()
            sl_price = round(recent_low - (0.4 * atr_val), 3)
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
                    f"Volatility cycle transition: Compression ({comp_data['compression_ratio']}x) -> Expansion ({comp_data['current_ratio']}x)",
                    f"Bullish expansion candle confirmed with positive EMA slope",
                    f"Targeting momentum continuation to {tp_price:.2f}"
                ],
                metadata={"compression_ratio": comp_data["compression_ratio"], "current_ratio": comp_data["current_ratio"]}
            )

        # ─── ATR EXPANSION SELL ───
        elif close_p < open_p and (ema_data["bearish"] or regime_report.regime == MarketRegime.TRENDING_DOWN or ema_data["fast_slope"] < 0):
            recent_high = df_entry["high"].iloc[-5:].max()
            sl_price = round(recent_high + (0.4 * atr_val), 3)
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
                    f"Volatility cycle transition: Compression ({comp_data['compression_ratio']}x) -> Expansion ({comp_data['current_ratio']}x)",
                    f"Bearish expansion candle confirmed with negative EMA slope",
                    f"Targeting momentum continuation to {tp_price:.2f}"
                ],
                metadata={"compression_ratio": comp_data["compression_ratio"], "current_ratio": comp_data["current_ratio"]}
            )

        return None
