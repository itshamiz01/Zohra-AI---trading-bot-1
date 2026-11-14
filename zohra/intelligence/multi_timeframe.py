"""
╔══════════════════════════════════════════════════════════════════════╗
║         ZOHRA — MULTI-TIMEFRAME ANALYSIS ENGINE                      ║
║    Institutional-Grade Timeframe Confluence Across All Markets       ║
╚══════════════════════════════════════════════════════════════════════╝

Never execute a trade using only one timeframe.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from zohra.intelligence.models import TimeframeAlignment, TimeframeResult
from zohra.config.settings import INTELLIGENCE_MTF_TIMEFRAMES, INTELLIGENCE_MIN_TF_ALIGNMENT

logger = logging.getLogger("zohra.intelligence.mtf")

# Timeframe importance weights (higher = more influence on combined score)
TF_WEIGHTS = {
    "MN": 1.0, "W1": 0.95, "D1": 0.90, "H12": 0.80, "H8": 0.75,
    "H4": 0.70, "H2": 0.60, "H1": 0.55, "M30": 0.45, "M15": 0.40,
    "M5": 0.30, "M3": 0.20, "M1": 0.10,
}

# Timeframes considered "higher" for bias determination
HIGHER_TIMEFRAMES = {"MN", "W1", "D1", "H4"}


class MultiTimeframeEngine:
    """
    Analyzes a symbol across all configured timeframes to identify
    trend alignment, detect conflicts, and produce a combined confidence
    score that controls trade approval.
    """

    def __init__(self):
        self.timeframes = INTELLIGENCE_MTF_TIMEFRAMES
        self.min_alignment = INTELLIGENCE_MIN_TF_ALIGNMENT

    def analyze(self, symbol: str, broker: str = "mt5") -> TimeframeAlignment:
        """
        Run multi-timeframe analysis for a symbol.
        Returns a TimeframeAlignment with per-TF results and combined confidence.
        """
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return TimeframeAlignment(symbol=symbol, is_aligned=False, combined_confidence=0.0, higher_tf_bias="NONE", results=[])

        results: List[TimeframeResult] = []
        broker_manager = self._get_broker_manager()

        for tf in self.timeframes:
            try:
                df = self._fetch_ohlcv(broker_manager, symbol, tf, broker, count=100)
                if df is not None and len(df) >= 30:
                    result = self._analyze_single_tf(df, tf)
                    results.append(result)
            except Exception as e:
                logger.debug(f"MTF skip {symbol}/{tf}: {e}")

        if not results:
            return TimeframeAlignment(symbol=symbol, combined_confidence=0.0)

        # Count aligned directions
        bullish = sum(1 for r in results if r.trend_direction == "BULLISH")
        bearish = sum(1 for r in results if r.trend_direction == "BEARISH")
        total = len(results)

        dominant = "BULLISH" if bullish > bearish else "BEARISH" if bearish > bullish else "NEUTRAL"
        aligned = max(bullish, bearish)

        # Higher-timeframe bias
        htf_results = [r for r in results if r.timeframe in HIGHER_TIMEFRAMES]
        htf_bullish = sum(1 for r in htf_results if r.trend_direction == "BULLISH")
        htf_bearish = sum(1 for r in htf_results if r.trend_direction == "BEARISH")
        htf_bias = "BULLISH" if htf_bullish > htf_bearish else "BEARISH" if htf_bearish > htf_bullish else "NEUTRAL"

        # Conflicts
        conflicts = []
        if htf_bias != "NEUTRAL" and dominant != htf_bias:
            conflicts.append(f"HTF bias ({htf_bias}) conflicts with dominant direction ({dominant})")
        for r in results:
            if r.trend_direction != "NEUTRAL" and r.trend_direction != dominant:
                conflicts.append(f"{r.timeframe} disagrees ({r.trend_direction} vs {dominant})")

        # Execution timeframe: best lower-TF with alignment
        execution_tf = "M15"
        for tf_name in ["M15", "M5", "M30", "H1"]:
            matching = [r for r in results if r.timeframe == tf_name and r.trend_direction == dominant]
            if matching:
                execution_tf = tf_name
                break

        # Combined weighted confidence
        combined = self._compute_weighted_confidence(results, dominant)

        return TimeframeAlignment(
            symbol=symbol,
            results=results,
            aligned_count=aligned,
            total_analyzed=total,
            dominant_direction=dominant,
            higher_tf_bias=htf_bias,
            execution_timeframe=execution_tf,
            conflicts=conflicts,
            combined_confidence=combined,
        )

    # ─── Single Timeframe Analysis ────────────────────────────

    def _analyze_single_tf(self, df: pd.DataFrame, tf: str) -> TimeframeResult:
        """Analyze one timeframe: EMA alignment, RSI, ADX, structure."""
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        # EMA alignment
        ema_fast = self._ema(close, 9)
        ema_mid = self._ema(close, 21)
        ema_slow = self._ema(close, 50)

        bullish_ema = ema_fast[-1] > ema_mid[-1] > ema_slow[-1]
        bearish_ema = ema_fast[-1] < ema_mid[-1] < ema_slow[-1]
        ema_aligned = bullish_ema or bearish_ema

        # RSI
        rsi = self._rsi(close, 14)

        # ADX
        adx = self._adx(high, low, close, 14)

        # Structure: check last 2 swing highs and lows
        structure = self._detect_structure(high, low)

        # Determine trend direction
        if bullish_ema and rsi > 45:
            direction = "BULLISH"
        elif bearish_ema and rsi < 55:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # Confidence for this TF
        tf_conf = 0.0
        if direction != "NEUTRAL":
            tf_conf += 30 if ema_aligned else 10
            tf_conf += min(30, adx)  # ADX contributes up to 30
            if direction == "BULLISH" and rsi > 50:
                tf_conf += 20
            elif direction == "BEARISH" and rsi < 50:
                tf_conf += 20
            if structure in ("HH_HL", "LH_LL"):
                tf_conf += 20

        return TimeframeResult(
            timeframe=tf,
            trend_direction=direction,
            ema_aligned=ema_aligned,
            rsi=round(rsi, 2),
            adx=round(adx, 2),
            structure=structure,
            confidence=round(min(100, tf_conf), 1),
        )

    # ─── Weighted Confidence ──────────────────────────────────

    def _compute_weighted_confidence(self, results: List[TimeframeResult], dominant: str) -> float:
        """Compute a combined confidence score weighted by timeframe importance."""
        if not results or dominant == "NEUTRAL":
            return 0.0

        weighted_sum = 0.0
        weight_total = 0.0

        for r in results:
            w = TF_WEIGHTS.get(r.timeframe, 0.3)
            if r.trend_direction == dominant:
                weighted_sum += r.confidence * w
            else:
                weighted_sum -= r.confidence * w * 0.3  # Penalty for disagreement
            weight_total += w

        raw = weighted_sum / max(weight_total, 1e-9)
        return round(max(0, min(100, raw)), 1)

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
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        if len(high) < period + 1:
            return 0.0
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))
        atr = np.mean(tr[-period:])
        if atr < 1e-9:
            return 0.0
        plus_dm = np.where((np.diff(high) > -np.diff(low)) & (np.diff(high) > 0), np.diff(high), 0)
        minus_dm = np.where((-np.diff(low) > np.diff(high)) & (-np.diff(low) > 0), -np.diff(low), 0)
        plus_di = 100 * np.mean(plus_dm[-period:]) / atr
        minus_di = 100 * np.mean(minus_dm[-period:]) / atr
        if plus_di + minus_di == 0:
            return 0.0
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx

    @staticmethod
    def _detect_structure(high: np.ndarray, low: np.ndarray) -> str:
        """Detect HH/HL (bullish) or LH/LL (bearish) structure from last swings."""
        if len(high) < 20:
            return "NONE"
        # Simple pivot detection over last 20 bars
        pivot_highs = []
        pivot_lows = []
        for i in range(5, len(high) - 5):
            if high[i] == max(high[i - 5:i + 5 + 1]):
                pivot_highs.append(high[i])
            if low[i] == min(low[i - 5:i + 5 + 1]):
                pivot_lows.append(low[i])

        if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
            hh = pivot_highs[-1] > pivot_highs[-2]
            hl = pivot_lows[-1] > pivot_lows[-2]
            lh = pivot_highs[-1] < pivot_highs[-2]
            ll = pivot_lows[-1] < pivot_lows[-2]
            if hh and hl:
                return "HH_HL"
            if lh and ll:
                return "LH_LL"
            return "MIXED"
        return "NONE"

    # ─── Data Access ──────────────────────────────────────────

    @staticmethod
    def _get_broker_manager():
        try:
            from zohra.brokers.manager import broker_manager
            return broker_manager
        except ImportError:
            return None

    @staticmethod
    def _fetch_ohlcv(broker_manager, symbol: str, tf: str, broker: str, count: int = 100) -> Optional[pd.DataFrame]:
        if broker_manager is None:
            return None
        try:
            return broker_manager.get_ohlcv(symbol, tf, count=count, broker=broker)
        except Exception:
            return None


# Singleton
mtf_engine = MultiTimeframeEngine()
