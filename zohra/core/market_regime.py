"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — 9-STATE MARKET REGIME ENGINE                    ║
║          Institutional Multi-Indicator Market Classification         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np

from zohra.core.enums import MarketRegime
from zohra.indicators.ema import check_ema_alignment, calculate_ema
from zohra.indicators.adx import calculate_adx
from zohra.indicators.atr import calculate_atr, calculate_relative_atr_expansion
from zohra.indicators.bollinger import calculate_bollinger_bands
from zohra.indicators.vwap import calculate_session_vwap
from zohra.indicators.market_structure import detect_market_structure
from zohra.config.strategy_config import strategy_config, REGIME_ENGINE_CONFIG

logger = logging.getLogger("zohra.market_regime")


@dataclass
class RegimeReport:
    """Comprehensive structured report output by the Market Regime Engine."""
    regime: MarketRegime
    confidence: int                     # 0 to 100
    explanation: str = ""
    adx_value: float = 0.0
    ema_alignment: str = "FLAT"         # BULLISH, BEARISH, FLAT
    ema_slope_strength: str = "FLAT"
    adx_trending: bool = False
    atr_state: str = "NORMAL"
    expansion_ratio: float = 1.0
    vwap_slope: float = 0.0
    vwap_crossings: int = 0
    bandwidth: float = 0.0
    spread_ok: bool = True
    reasons: List[str] = field(default_factory=list)
    structure: str = "RANGING"          # BULLISH_TREND, BEARISH_TREND, RANGING
    metrics: Dict[str, Any] = field(default_factory=dict)


class MarketRegimeEngine:
    """
    Classifies XAUUSD market conditions into one of 9 distinct regimes:
    TRENDING_UP, TRENDING_DOWN, RANGING, ROTATIONAL, BREAKOUT_EXPANSION,
    HIGH_VOLATILITY, LOW_LIQUIDITY, NEWS_OR_ABNORMAL_VOLATILITY, UNCLEAR.
    """

    def __init__(self, config=None, *, adx_period=None, bb_period=None, atr_period=None):
        """Create an engine without mutating the shared strategy configuration.

        The keyword overrides retain support for the earlier public constructor
        while the current implementation continues to use the consolidated
        ``MarketRegimeConfig`` object.
        """
        self.config = deepcopy(config or strategy_config.regime)
        for name, value in {
            "adx_period": adx_period,
            "bb_period": bb_period,
            "atr_period": atr_period,
        }.items():
            if value is not None:
                setattr(self.config, name, value)

    def classify_regime(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame] = None,
                        current_spread_pips: float = 2.0) -> RegimeReport:
        """
        Classifies market regime using quantitative indicators across entry and HTF timeframes.
        """
        if df_entry is None or len(df_entry) < 25:
            return RegimeReport(
                regime=MarketRegime.UNCLEAR,
                confidence=50,
                explanation="Insufficient candle history to determine market regime.",
                reasons=["Insufficient candle history to determine market regime."]
            )

        # 1. Calculate Core Indicators
        ema_info = check_ema_alignment(df_entry, fast=9, slow=21, trend=50)
        adx_dict = calculate_adx(df_entry, period=self.config.adx_period)
        adx = float(adx_dict.get("latest_adx", 0.0))
        pdi = float(adx_dict.get("latest_plus_di", 0.0))
        mdi = float(adx_dict.get("latest_minus_di", 0.0))

        atr_exp = calculate_relative_atr_expansion(df_entry)
        expansion_ratio = atr_exp["expansion_ratio"]
        current_atr = atr_exp["current_atr"]

        bb_dict = calculate_bollinger_bands(df_entry, period=self.config.bb_period, num_std=self.config.bb_std)
        bandwidth = bb_dict["latest_bandwidth"]

        vwap_dict = calculate_session_vwap(df_entry)
        crossings = vwap_dict["cross_count"]

        structure_info = detect_market_structure(df_entry)

        # 2. Evaluate HTF Bias
        htf_bullish = False
        htf_bearish = False
        if df_htf is not None and len(df_htf) >= 20:
            htf_ema = check_ema_alignment(df_htf, fast=9, slow=21, trend=50)
            htf_bullish = htf_ema["bullish"]
            htf_bearish = htf_ema["bearish"]

        # 3. Spread Filter Check
        spread_ok = current_spread_pips <= 4.5
        reasons = []

        # Detect a discrete shock as well as sustained ATR expansion. A single
        # news candle can be far larger than its recent peers before the ATR
        # average has caught up, so relying on the expansion ratio alone lets
        # the first shock through as a normal range or trend.
        candle_ranges = (df_entry["high"] - df_entry["low"]).astype(float)
        prior_ranges = candle_ranges.iloc[-21:-1]
        typical_range = float(prior_ranges.median()) if not prior_ranges.empty else 0.0
        last_range = float(candle_ranges.iloc[-1])
        last_body = abs(float(df_entry["close"].iloc[-1]) - float(df_entry["open"].iloc[-1]))
        abnormal_candle = typical_range > 0 and (
            last_range >= typical_range * 4.0 or last_body >= typical_range * 3.0
        )

        # 4. Multi-Condition Decision Tree
        # A. Abnormal Volatility / Spread Spikes
        if not spread_ok or expansion_ratio >= 2.5 or abnormal_candle:
            regime = MarketRegime.NEWS_OR_ABNORMAL_VOLATILITY
            confidence = 88
            reasons.append(
                f"Abnormal volatility (ATR ratio={expansion_ratio}x, candle range={last_range:.5f}, "
                f"baseline={typical_range:.5f}) or elevated spread ({current_spread_pips} pips)"
            )

        # B. Breakout Expansion
        elif expansion_ratio >= self.config.atr_expansion_threshold and adx >= self.config.adx_trend_threshold and abs(ema_info["fast_slope"]) > 0.4:
            regime = MarketRegime.BREAKOUT_EXPANSION
            confidence = min(95, int(60 + adx + (expansion_ratio * 10)))
            reasons.append(f"Volatility breakout expansion active (ATR ratio={expansion_ratio}, ADX={adx})")

        # C. Trending UP
        elif (ema_info["bullish"] and adx >= 22.0) or (pdi > mdi and adx >= self.config.adx_trend_threshold and ema_info["fast_slope"] > 0):
            regime = MarketRegime.TRENDING_UP
            base_conf = 65
            if ema_info["slope_strength"] == "STRONG":
                base_conf += 15
            if htf_bullish:
                base_conf += 10
            if structure_info["structure"] == "BULLISH_TREND":
                base_conf += 10
            confidence = min(98, base_conf)
            reasons.append(f"Bullish EMA stack + Higher Highs/Lows structure (ADX={adx}, +DI={pdi})")

        # D. Trending DOWN
        elif (ema_info["bearish"] and adx >= 22.0) or (mdi > pdi and adx >= self.config.adx_trend_threshold and ema_info["fast_slope"] < 0):
            regime = MarketRegime.TRENDING_DOWN
            base_conf = 65
            if ema_info["slope_strength"] == "STRONG":
                base_conf += 15
            if htf_bearish:
                base_conf += 10
            if structure_info["structure"] == "BEARISH_TREND":
                base_conf += 10
            confidence = min(98, base_conf)
            reasons.append(f"Bearish EMA stack + Lower Highs/Lows structure (ADX={adx}, -DI={mdi})")

        # E. Rotational Market
        elif crossings >= 3 and adx < self.config.adx_trend_threshold:
            regime = MarketRegime.ROTATIONAL
            confidence = min(90, 60 + (crossings * 5))
            reasons.append(f"Rotational price action oscillating around VWAP ({crossings} crossings in 20 bars, ADX={adx})")

        # F. Ranging / Compression
        elif (adx < self.config.adx_trend_threshold) or bandwidth <= self.config.bollinger_bandwidth_compression_threshold:
            regime = MarketRegime.RANGING
            confidence = 80 if bandwidth <= self.config.bollinger_bandwidth_compression_threshold else 72
            reasons.append(f"Flat EMAs and low directional index (ADX={adx}, Bandwidth={bandwidth:.4f})")

        # Fallback / Unclear
        else:
            regime = MarketRegime.UNCLEAR
            confidence = 50
            reasons.append(f"Conflicting signals: ADX={adx}, Slope={ema_info['fast_slope']}, Bandwidth={bandwidth:.4f}")

        metrics = {
            "adx": adx,
            "plus_di": pdi,
            "minus_di": mdi,
            "ema_fast": ema_info["fast_ema"],
            "ema_slow": ema_info["slow_ema"],
            "ema_slope": ema_info["fast_slope"],
            "expansion_ratio": expansion_ratio,
            "bandwidth": bandwidth,
            "vwap_crossings": crossings,
            "structure": structure_info["structure"]
        }
        if expansion_ratio >= self.config.atr_expansion_threshold:
            atr_state = "EXPANSION"
        elif expansion_ratio <= 0.85:
            atr_state = "COMPRESSION"
        else:
            atr_state = "NORMAL"

        return RegimeReport(
            regime=regime,
            confidence=confidence,
            explanation="; ".join(reasons),
            adx_value=adx,
            ema_alignment=ema_info["alignment"],
            ema_slope_strength=ema_info.get("slope_strength", "FLAT"),
            adx_trending=adx >= self.config.adx_trend_threshold,
            atr_state=atr_state,
            expansion_ratio=expansion_ratio,
            vwap_slope=float(vwap_dict.get("slope", 0.0) or 0.0),
            vwap_crossings=crossings,
            bandwidth=bandwidth,
            spread_ok=spread_ok,
            reasons=reasons,
            structure=structure_info["structure"],
            metrics=metrics
        )

    def classify(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Backward compatibility helper returning dict representation."""
        report = self.classify_regime(df)
        return {
            "regime": report.regime,
            "confidence": report.confidence,
            "explanation": "; ".join(report.reasons),
            "metrics": report.metrics
        }

    def detect_with_details(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Return the legacy decision-engine vocabulary with verified details.

        The newer classifier deliberately distinguishes bullish and bearish
        trends.  The older decision pipeline only routes a generic trend, so
        this adapter translates categories without discarding the detailed
        report exposed in ``metrics``.
        """
        report = self.classify_regime(df)
        legacy_regime = {
            MarketRegime.TRENDING_UP: MarketRegime.TRENDING,
            MarketRegime.TRENDING_DOWN: MarketRegime.TRENDING,
            MarketRegime.BREAKOUT_EXPANSION: MarketRegime.BREAKOUT,
            MarketRegime.NEWS_OR_ABNORMAL_VOLATILITY: MarketRegime.NEWS_DRIVEN,
            MarketRegime.ROTATIONAL: MarketRegime.RANGING,
        }.get(report.regime, report.regime)
        return {
            "regime": legacy_regime,
            "confidence": report.confidence,
            "explanation": report.explanation,
            "metrics": report.metrics,
            "report": report,
        }

    def detect(self, df: pd.DataFrame) -> MarketRegime:
        """Compatibility helper returning single MarketRegime enum."""
        return self.detect_with_details(df)["regime"]


# Master singleton instances
market_regime_engine = MarketRegimeEngine()
regime_engine = market_regime_engine
regime_detector = market_regime_engine
MarketRegimeDetector = MarketRegimeEngine  # Alias for backward compatibility
