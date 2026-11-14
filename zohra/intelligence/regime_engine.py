"""
╔══════════════════════════════════════════════════════════════════════╗
║         ZOHRA — ENHANCED MARKET REGIME DETECTION ENGINE              ║
║   AI-Driven Regime Classification with Dynamic Adjustments          ║
╚══════════════════════════════════════════════════════════════════════╝

Extends the existing MarketRegimeDetector with 21 enhanced regime
classifications and dynamic parameter adjustment engine.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from zohra.intelligence.models import RegimeState, RegimeAdjustments, EnhancedRegime

logger = logging.getLogger("zohra.intelligence.regime")


class RegimeDetectionEngine:
    """
    Enhanced market regime detection engine that classifies markets into
    21 distinct states and dynamically adjusts risk, sizing, strategy
    selection, and execution frequency.
    """

    def __init__(self):
        self._history: Dict[str, List[Dict[str, Any]]] = {}

        # Regime → adjustment profiles
        self._adjustment_map: Dict[str, RegimeAdjustments] = {
            EnhancedRegime.STRONG_TREND.value: RegimeAdjustments(
                risk_multiplier=1.2, position_size_multiplier=1.2,
                confidence_threshold=65, preferred_strategies=["trend_following", "momentum"],
                execution_frequency="aggressive",
            ),
            EnhancedRegime.WEAK_TREND.value: RegimeAdjustments(
                risk_multiplier=0.8, position_size_multiplier=0.8,
                confidence_threshold=75, preferred_strategies=["trend_following", "scalping"],
                execution_frequency="normal",
            ),
            EnhancedRegime.BULL_MARKET.value: RegimeAdjustments(
                risk_multiplier=1.1, position_size_multiplier=1.1,
                confidence_threshold=65, preferred_strategies=["trend_following", "breakout", "momentum"],
                execution_frequency="aggressive",
            ),
            EnhancedRegime.BEAR_MARKET.value: RegimeAdjustments(
                risk_multiplier=0.7, position_size_multiplier=0.7,
                confidence_threshold=80, preferred_strategies=["mean_reversion", "scalping"],
                execution_frequency="conservative",
            ),
            EnhancedRegime.RANGING.value: RegimeAdjustments(
                risk_multiplier=0.8, position_size_multiplier=0.8,
                confidence_threshold=75, preferred_strategies=["mean_reversion", "scalping"],
                execution_frequency="normal",
            ),
            EnhancedRegime.SIDEWAYS.value: RegimeAdjustments(
                risk_multiplier=0.6, position_size_multiplier=0.6,
                confidence_threshold=80, preferred_strategies=["mean_reversion"],
                execution_frequency="conservative",
            ),
            EnhancedRegime.EXPANSION.value: RegimeAdjustments(
                risk_multiplier=1.0, position_size_multiplier=1.0,
                confidence_threshold=70, preferred_strategies=["breakout", "momentum", "trend_following"],
                execution_frequency="aggressive",
            ),
            EnhancedRegime.CONSOLIDATION.value: RegimeAdjustments(
                risk_multiplier=0.5, position_size_multiplier=0.5,
                confidence_threshold=80, preferred_strategies=["mean_reversion"],
                execution_frequency="conservative",
            ),
            EnhancedRegime.VOLATILITY_EXPANSION.value: RegimeAdjustments(
                risk_multiplier=0.6, position_size_multiplier=0.5,
                confidence_threshold=85, preferred_strategies=["breakout"],
                execution_frequency="conservative",
            ),
            EnhancedRegime.VOLATILITY_COMPRESSION.value: RegimeAdjustments(
                risk_multiplier=0.7, position_size_multiplier=0.7,
                confidence_threshold=75, preferred_strategies=["breakout", "scalping"],
                execution_frequency="normal",
            ),
            EnhancedRegime.BREAKOUT_PHASE.value: RegimeAdjustments(
                risk_multiplier=1.0, position_size_multiplier=1.0,
                confidence_threshold=70, preferred_strategies=["breakout", "momentum"],
                execution_frequency="aggressive",
            ),
            EnhancedRegime.REVERSAL_PHASE.value: RegimeAdjustments(
                risk_multiplier=0.5, position_size_multiplier=0.5,
                confidence_threshold=85, preferred_strategies=["mean_reversion", "smart_money"],
                execution_frequency="conservative",
            ),
            EnhancedRegime.ACCUMULATION.value: RegimeAdjustments(
                risk_multiplier=0.8, position_size_multiplier=0.8,
                confidence_threshold=75, preferred_strategies=["smart_money", "wyckoff"],
                execution_frequency="normal",
            ),
            EnhancedRegime.DISTRIBUTION.value: RegimeAdjustments(
                risk_multiplier=0.6, position_size_multiplier=0.6,
                confidence_threshold=80, preferred_strategies=["smart_money", "wyckoff"],
                execution_frequency="conservative",
            ),
            EnhancedRegime.PANIC_SELLING.value: RegimeAdjustments(
                risk_multiplier=0.3, position_size_multiplier=0.3,
                confidence_threshold=90, preferred_strategies=[],
                execution_frequency="paused",
            ),
            EnhancedRegime.RECOVERY.value: RegimeAdjustments(
                risk_multiplier=0.7, position_size_multiplier=0.7,
                confidence_threshold=75, preferred_strategies=["trend_following", "momentum"],
                execution_frequency="normal",
            ),
            EnhancedRegime.RISK_ON.value: RegimeAdjustments(
                risk_multiplier=1.1, position_size_multiplier=1.1,
                confidence_threshold=65, preferred_strategies=["trend_following", "breakout", "momentum"],
                execution_frequency="aggressive",
            ),
            EnhancedRegime.RISK_OFF.value: RegimeAdjustments(
                risk_multiplier=0.5, position_size_multiplier=0.5,
                confidence_threshold=85, preferred_strategies=["mean_reversion"],
                execution_frequency="conservative",
            ),
            EnhancedRegime.LIQUIDITY_DRIVEN.value: RegimeAdjustments(
                risk_multiplier=0.8, position_size_multiplier=0.8,
                confidence_threshold=75, preferred_strategies=["smart_money"],
                execution_frequency="normal",
            ),
            EnhancedRegime.NEWS_DRIVEN.value: RegimeAdjustments(
                risk_multiplier=0.3, position_size_multiplier=0.3,
                confidence_threshold=90, preferred_strategies=[],
                execution_frequency="paused",
            ),
            EnhancedRegime.INSTITUTIONAL_ACTIVITY.value: RegimeAdjustments(
                risk_multiplier=0.9, position_size_multiplier=0.9,
                confidence_threshold=70, preferred_strategies=["smart_money", "trend_following"],
                execution_frequency="normal",
            ),
        }

    def detect(self, df: pd.DataFrame, symbol: str = "") -> RegimeState:
        """
        Detect the enhanced market regime from OHLCV data.
        Returns a RegimeState with the detected regime and adjustments.
        """
        if df is None or len(df) < 50:
            return RegimeState(symbol=symbol, primary_regime="ranging",
                             enhanced_regime=EnhancedRegime.SIDEWAYS.value, confidence=0.0)

        close = df["close"].values.astype(float)
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        volume = df["tick_volume"].values.astype(float) if "tick_volume" in df.columns else np.ones(len(df))

        # Core indicators
        adx = self._compute_adx(high, low, close)
        atr = self._compute_atr(high, low, close)
        atr_pct = atr / max(close[-1], 1e-9) * 100
        bb_width = self._compute_bb_width(close)
        ema_20 = self._ema(close, 20)
        ema_50 = self._ema(close, 50)
        rsi = self._rsi(close)
        trend = float(close[-1] - close[-20]) / max(abs(close[-20]), 1e-9) * 100

        vol_recent = float(np.mean(volume[-5:]))
        vol_avg = float(np.mean(volume[-20:]))
        vol_ratio = vol_recent / max(vol_avg, 1e-9)

        # Volatility state
        if atr_pct > 3.0:
            vol_state = "extreme"
        elif atr_pct > 1.5:
            vol_state = "high"
        elif atr_pct > 0.5:
            vol_state = "normal"
        else:
            vol_state = "low"

        # Enhanced regime classification
        enhanced = self._classify_enhanced(
            adx=adx, atr_pct=atr_pct, bb_width=bb_width,
            ema_20=ema_20, ema_50=ema_50, close=close,
            trend=trend, rsi=rsi, vol_ratio=vol_ratio, volume=volume,
        )

        # Map to primary regime (for backward compatibility with existing code)
        primary = self._enhanced_to_primary(enhanced)

        # Get adjustments
        adjustments = self._adjustment_map.get(enhanced, RegimeAdjustments())

        # Confidence
        confidence = self._compute_confidence(adx, atr_pct, bb_width, trend)

        # Record history
        entry = {"timestamp": datetime.utcnow().isoformat(), "regime": enhanced, "confidence": confidence}
        self._history.setdefault(symbol, []).append(entry)
        if len(self._history[symbol]) > 100:
            self._history[symbol] = self._history[symbol][-100:]

        return RegimeState(
            symbol=symbol,
            primary_regime=primary,
            enhanced_regime=enhanced,
            confidence=round(confidence, 1),
            volatility_state=vol_state,
            adjustments=adjustments,
            history=self._history.get(symbol, [])[-10:],
        )

    # ─── Enhanced Classification ──────────────────────────────

    def _classify_enhanced(self, adx: float, atr_pct: float, bb_width: float,
                            ema_20: np.ndarray, ema_50: np.ndarray, close: np.ndarray,
                            trend: float, rsi: float, vol_ratio: float,
                            volume: np.ndarray) -> str:
        """Classify into one of 21 enhanced regimes."""

        bullish_ema = float(ema_20[-1]) > float(ema_50[-1])
        bearish_ema = float(ema_20[-1]) < float(ema_50[-1])

        # Panic selling: large drop + extreme volume
        if trend < -5 and vol_ratio > 2.0 and rsi < 25:
            return EnhancedRegime.PANIC_SELLING.value

        # News driven: extreme ATR spike
        body = abs(float(close[-1]) - float(close[-2]))
        if atr_pct > 0 and body > self._compute_atr(
            close[:1].astype(float) if len(close) < 2 else np.array([0.0]),
            close[:1].astype(float) if len(close) < 2 else np.array([0.0]),
            close
        ) * 3:
            pass  # Handled below

        if atr_pct > 3.0 and vol_ratio > 1.8:
            return EnhancedRegime.NEWS_DRIVEN.value

        # Strong trend
        if adx > 35 and abs(trend) > 3:
            if trend > 0:
                return EnhancedRegime.STRONG_TREND.value if bullish_ema else EnhancedRegime.BULL_MARKET.value
            else:
                return EnhancedRegime.STRONG_TREND.value if bearish_ema else EnhancedRegime.BEAR_MARKET.value

        # Breakout phase
        if adx > 25 and bb_width > 2.0 and atr_pct > 1.0:
            return EnhancedRegime.BREAKOUT_PHASE.value

        # Volatility expansion
        if atr_pct > 2.0 and bb_width > 2.5:
            return EnhancedRegime.VOLATILITY_EXPANSION.value

        # Volatility compression
        if atr_pct < 0.3 and bb_width < 1.0:
            return EnhancedRegime.VOLATILITY_COMPRESSION.value

        # Weak trend
        if 20 < adx <= 35 and abs(trend) > 1:
            return EnhancedRegime.WEAK_TREND.value

        # Recovery
        if trend > 2 and rsi > 40 and rsi < 60 and vol_ratio > 1.0:
            return EnhancedRegime.RECOVERY.value

        # Reversal phase
        if adx > 20 and ((trend > 0 and rsi > 70) or (trend < 0 and rsi < 30)):
            return EnhancedRegime.REVERSAL_PHASE.value

        # Institutional activity: high volume, moderate trend
        if vol_ratio > 1.5 and adx > 20:
            return EnhancedRegime.INSTITUTIONAL_ACTIVITY.value

        # Expansion
        if bb_width > 2.0 and abs(trend) > 1:
            return EnhancedRegime.EXPANSION.value

        # Consolidation
        if bb_width < 1.5 and adx < 20:
            return EnhancedRegime.CONSOLIDATION.value

        # Risk-on / Risk-off (simplified)
        if trend > 1 and rsi > 55:
            return EnhancedRegime.RISK_ON.value
        if trend < -1 and rsi < 45:
            return EnhancedRegime.RISK_OFF.value

        # Accumulation / Distribution
        if adx < 20 and bb_width < 1.5:
            if vol_ratio > 1.2:
                return EnhancedRegime.ACCUMULATION.value if trend >= 0 else EnhancedRegime.DISTRIBUTION.value

        # Ranging / Sideways
        if adx < 20:
            return EnhancedRegime.RANGING.value

        return EnhancedRegime.SIDEWAYS.value

    # ─── Backward Compatibility ───────────────────────────────

    @staticmethod
    def _enhanced_to_primary(enhanced: str) -> str:
        """Map enhanced regime to the 6 primary regimes for backward compatibility."""
        mapping = {
            "strong_trend": "trending", "weak_trend": "trending",
            "bull_market": "trending", "bear_market": "trending",
            "ranging": "ranging", "sideways": "ranging",
            "expansion": "breakout", "breakout_phase": "breakout",
            "volatility_expansion": "high_volatility", "volatility_compression": "ranging",
            "consolidation": "ranging", "reversal_phase": "trending",
            "accumulation": "ranging", "distribution": "ranging",
            "panic_selling": "high_volatility", "recovery": "trending",
            "risk_on": "trending", "risk_off": "ranging",
            "liquidity_driven": "trending", "news_driven": "news_driven",
            "institutional_activity": "trending",
        }
        return mapping.get(enhanced, "ranging")

    # ─── Technical Helpers ────────────────────────────────────

    @staticmethod
    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        alpha = 2.0 / (period + 1)
        result = np.zeros_like(data, dtype=float)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    @staticmethod
    def _rsi(close: np.ndarray, period: int = 14) -> float:
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        return 100 - (100 / (1 + avg_gain / avg_loss))

    @staticmethod
    def _compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        if len(high) < period + 1:
            return 0.0
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        atr = np.mean(tr[-period:])
        if atr < 1e-9:
            return 0.0
        plus_dm = np.where((np.diff(high) > -np.diff(low)) & (np.diff(high) > 0), np.diff(high), 0)
        minus_dm = np.where((-np.diff(low) > np.diff(high)) & (-np.diff(low) > 0), -np.diff(low), 0)
        plus_di = 100 * np.mean(plus_dm[-period:]) / atr
        minus_di = 100 * np.mean(minus_dm[-period:]) / atr
        if plus_di + minus_di == 0:
            return 0.0
        return 100 * abs(plus_di - minus_di) / (plus_di + minus_di)

    @staticmethod
    def _compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        if len(high) < period + 1:
            return 0.0
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        return float(np.mean(tr[-period:]))

    @staticmethod
    def _compute_bb_width(close: np.ndarray, period: int = 20) -> float:
        if len(close) < period:
            return 0.0
        sma = float(np.mean(close[-period:]))
        std = float(np.std(close[-period:]))
        return (std * 4) / max(sma, 1e-9) * 100  # Width as % of price

    @staticmethod
    def _compute_confidence(adx: float, atr_pct: float, bb_width: float, trend: float) -> float:
        conf = 50.0
        if adx > 30:
            conf += 15
        elif adx > 20:
            conf += 8
        if abs(trend) > 3:
            conf += 15
        elif abs(trend) > 1:
            conf += 8
        if bb_width > 2.0:
            conf += 5
        return min(100, conf)

    # ─── Convenience ──────────────────────────────────────────

    def get_regime(self, symbol: str) -> Dict[str, Any]:
        """Get the latest regime state as a dict (for API)."""
        # Try to use existing data from broker
        try:
            from zohra.brokers.manager import broker_manager
            df = broker_manager.get_ohlcv(symbol, "H1", count=100)
            if df is not None and len(df) >= 50:
                return self.detect(df, symbol).to_dict()
        except Exception:
            pass
        return RegimeState(symbol=symbol).to_dict()


# Singleton
regime_engine = RegimeDetectionEngine()
