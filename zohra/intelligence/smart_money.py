"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — SMART MONEY INTELLIGENCE ENGINE                    ║
║   Universal ICT/SMC Framework Across Forex, Indian Markets, Crypto  ║
╚══════════════════════════════════════════════════════════════════════╝

Provides AI confidence based on institutional behavior, not indicators alone.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from zohra.intelligence.models import (
    SmartMoneySignal, OrderBlock, FairValueGap, LiquidityZone, WyckoffPhase,
)
from zohra.config.settings import INTELLIGENCE_SMC_MIN_CONFLUENCE

logger = logging.getLogger("zohra.intelligence.smc")


class SmartMoneyEngine:
    """
    Universal Smart Money Concepts engine working across all asset classes.
    Detects liquidity, order blocks, FVGs, BOS/CHoCH, Wyckoff phases,
    displacement, and institutional candles.
    """

    def __init__(self):
        self.min_confluence = INTELLIGENCE_SMC_MIN_CONFLUENCE

    def analyze(self, df: pd.DataFrame, symbol: str = "", timeframe: str = "M15") -> SmartMoneySignal:
        """
        Run full smart money analysis on OHLCV data.
        Returns SmartMoneySignal with all detected elements and confidence.
        """
        if df is None or len(df) < 30:
            return SmartMoneySignal(symbol=symbol, timeframe=timeframe, confidence=0.0)

        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        close = df["close"].values.astype(float)
        open_ = df["open"].values.astype(float)
        volume = df["tick_volume"].values.astype(float) if "tick_volume" in df.columns else np.ones(len(df))

        # Detect all elements
        order_blocks = self._detect_order_blocks(open_, high, low, close, volume)
        fvgs = self._detect_fair_value_gaps(high, low, close)
        liquidity = self._detect_liquidity_zones(high, low, close)
        bos = self._detect_bos(high, low)
        choch = self._detect_choch(high, low)
        premium, discount = self._detect_premium_discount(high, low, close)
        displacement = self._detect_displacement(open_, close, high, low)
        institutional = self._detect_institutional_candle(open_, close, high, low, volume)
        wyckoff = self._detect_wyckoff_phase(close, volume)

        # Confluence count
        confluence = 0
        if order_blocks:
            confluence += 1
        if fvgs:
            confluence += 1
        if liquidity:
            confluence += 1
        if bos:
            confluence += 1
        if choch:
            confluence += 1
        if premium or discount:
            confluence += 1
        if displacement:
            confluence += 1
        if institutional:
            confluence += 1

        # Confidence based on confluence
        confidence = min(100.0, confluence * 12.5)

        # Directional bias
        bullish_signals = 0
        bearish_signals = 0
        if bos and close[-1] > close[-2]:
            bullish_signals += 1
        if bos and close[-1] < close[-2]:
            bearish_signals += 1
        if choch and close[-1] > close[-5]:
            bullish_signals += 1
        if choch and close[-1] < close[-5]:
            bearish_signals += 1
        if discount:
            bullish_signals += 1
        if premium:
            bearish_signals += 1
        bullish_obs = sum(1 for ob in order_blocks if ob.type == "bullish")
        bearish_obs = sum(1 for ob in order_blocks if ob.type == "bearish")
        bullish_signals += bullish_obs
        bearish_signals += bearish_obs

        bias = "BULLISH" if bullish_signals > bearish_signals else "BEARISH" if bearish_signals > bullish_signals else "NEUTRAL"

        return SmartMoneySignal(
            symbol=symbol,
            timeframe=timeframe,
            order_blocks=order_blocks,
            fair_value_gaps=fvgs,
            liquidity_zones=liquidity,
            bos_detected=bos,
            choch_detected=choch,
            premium_zone=premium,
            discount_zone=discount,
            wyckoff_phase=wyckoff,
            displacement_detected=displacement,
            institutional_candle=institutional,
            confluence_count=confluence,
            confidence=round(confidence, 1),
            bias=bias,
        )

    # ─── Order Block Detection ────────────────────────────────

    @staticmethod
    def _detect_order_blocks(open_: np.ndarray, high: np.ndarray, low: np.ndarray,
                              close: np.ndarray, volume: np.ndarray) -> List[OrderBlock]:
        """Detect bullish and bearish order blocks."""
        obs: List[OrderBlock] = []
        if len(close) < 5:
            return obs

        for i in range(2, len(close) - 2):
            body = abs(close[i] - open_[i])
            prev_body = abs(close[i - 1] - open_[i - 1])

            # Bullish OB: bearish candle followed by strong bullish displacement
            if close[i - 1] < open_[i - 1] and close[i] > open_[i] and body > prev_body * 1.5:
                if close[i] > high[i - 1]:  # Displacement above prior high
                    obs.append(OrderBlock(
                        type="bullish",
                        high=float(high[i - 1]),
                        low=float(low[i - 1]),
                        origin_index=i - 1,
                        strength=round(body / max(prev_body, 1e-9), 2),
                        mitigated=float(low[-1]) < float(low[i - 1]),
                    ))

            # Bearish OB: bullish candle followed by strong bearish displacement
            if close[i - 1] > open_[i - 1] and close[i] < open_[i] and body > prev_body * 1.5:
                if close[i] < low[i - 1]:  # Displacement below prior low
                    obs.append(OrderBlock(
                        type="bearish",
                        high=float(high[i - 1]),
                        low=float(low[i - 1]),
                        origin_index=i - 1,
                        strength=round(body / max(prev_body, 1e-9), 2),
                        mitigated=float(high[-1]) > float(high[i - 1]),
                    ))

        return obs[-5:]  # Keep most recent 5

    # ─── Fair Value Gap Detection ─────────────────────────────

    @staticmethod
    def _detect_fair_value_gaps(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> List[FairValueGap]:
        """Detect standard and inverse FVGs."""
        fvgs: List[FairValueGap] = []
        if len(high) < 4:
            return fvgs

        for i in range(2, len(high)):
            # Bullish FVG: gap between candle i-2 high and candle i low
            if low[i] > high[i - 2]:
                fvgs.append(FairValueGap(
                    type="bullish",
                    high=float(low[i]),
                    low=float(high[i - 2]),
                    origin_index=i - 1,
                    filled=float(close[-1]) < float(low[i]),
                ))

            # Bearish FVG: gap between candle i low and candle i-2 high
            if high[i] < low[i - 2]:
                fvgs.append(FairValueGap(
                    type="bearish",
                    high=float(low[i - 2]),
                    low=float(high[i]),
                    origin_index=i - 1,
                    filled=float(close[-1]) > float(high[i]),
                ))

        return fvgs[-5:]

    # ─── Liquidity Zone Detection ─────────────────────────────

    @staticmethod
    def _detect_liquidity_zones(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> List[LiquidityZone]:
        """Detect internal/external liquidity and sweeps."""
        zones: List[LiquidityZone] = []
        if len(high) < 20:
            return zones

        # Equal highs (external liquidity above)
        recent_highs = high[-20:]
        for i in range(len(recent_highs) - 1):
            for j in range(i + 1, len(recent_highs)):
                if abs(recent_highs[i] - recent_highs[j]) / max(recent_highs[i], 1e-9) < 0.001:
                    swept = float(high[-1]) > float(recent_highs[i])
                    zones.append(LiquidityZone(
                        type="external" if swept else "internal",
                        level=float(recent_highs[i]),
                        touched_count=2,
                        swept=swept,
                    ))
                    break

        # Equal lows (external liquidity below)
        recent_lows = low[-20:]
        for i in range(len(recent_lows) - 1):
            for j in range(i + 1, len(recent_lows)):
                if abs(recent_lows[i] - recent_lows[j]) / max(recent_lows[i], 1e-9) < 0.001:
                    swept = float(low[-1]) < float(recent_lows[i])
                    zones.append(LiquidityZone(
                        type="external" if swept else "internal",
                        level=float(recent_lows[i]),
                        touched_count=2,
                        swept=swept,
                    ))
                    break

        return zones[:5]

    # ─── BOS / CHoCH Detection ────────────────────────────────

    @staticmethod
    def _detect_bos(high: np.ndarray, low: np.ndarray) -> bool:
        """Detect Break of Structure."""
        if len(high) < 10:
            return False
        recent_swing_high = max(high[-10:-1])
        recent_swing_low = min(low[-10:-1])
        return float(high[-1]) > float(recent_swing_high) or float(low[-1]) < float(recent_swing_low)

    @staticmethod
    def _detect_choch(high: np.ndarray, low: np.ndarray) -> bool:
        """Detect Change of Character (trend reversal)."""
        if len(high) < 15:
            return False
        # Was making higher highs, now lower high
        prev_highs = [max(high[i:i + 3]) for i in range(0, min(12, len(high) - 3), 3)]
        if len(prev_highs) >= 3:
            was_rising = prev_highs[-3] < prev_highs[-2]
            now_falling = prev_highs[-1] < prev_highs[-2]
            if was_rising and now_falling:
                return True
        return False

    # ─── Premium / Discount ───────────────────────────────────

    @staticmethod
    def _detect_premium_discount(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> tuple:
        """Detect if price is in premium or discount zone of the range."""
        if len(high) < 20:
            return False, False
        swing_high = float(max(high[-20:]))
        swing_low = float(min(low[-20:]))
        mid = (swing_high + swing_low) / 2
        current = float(close[-1])
        premium = current > mid + (swing_high - mid) * 0.5
        discount = current < mid - (mid - swing_low) * 0.5
        return premium, discount

    # ─── Displacement ─────────────────────────────────────────

    @staticmethod
    def _detect_displacement(open_: np.ndarray, close: np.ndarray,
                              high: np.ndarray, low: np.ndarray) -> bool:
        """Detect aggressive displacement candle (body > 2x ATR)."""
        if len(close) < 15:
            return False
        tr = np.maximum(high[-14:] - low[-14:],
                        np.maximum(np.abs(high[-14:] - close[-15:-1]),
                                   np.abs(low[-14:] - close[-15:-1])))
        atr = float(np.mean(tr))
        last_body = abs(float(close[-1]) - float(open_[-1]))
        return last_body > atr * 2

    # ─── Institutional Candle ─────────────────────────────────

    @staticmethod
    def _detect_institutional_candle(open_: np.ndarray, close: np.ndarray,
                                      high: np.ndarray, low: np.ndarray,
                                      volume: np.ndarray) -> bool:
        """Detect institutional-grade candle: large body, high volume."""
        if len(close) < 20:
            return False
        avg_body = float(np.mean(np.abs(close[-20:] - open_[-20:])))
        avg_vol = float(np.mean(volume[-20:]))
        last_body = abs(float(close[-1]) - float(open_[-1]))
        last_vol = float(volume[-1])
        return last_body > avg_body * 2 and last_vol > avg_vol * 1.5

    # ─── Wyckoff Phase ────────────────────────────────────────

    @staticmethod
    def _detect_wyckoff_phase(close: np.ndarray, volume: np.ndarray) -> str:
        """Simplified Wyckoff phase detection."""
        if len(close) < 30:
            return WyckoffPhase.UNKNOWN.value

        recent = close[-20:]
        older = close[-30:-20]

        recent_range = float(max(recent) - min(recent))
        older_range = float(max(older) - min(older))

        avg_vol_recent = float(np.mean(volume[-10:]))
        avg_vol_older = float(np.mean(volume[-30:-10]))

        trend = float(recent[-1] - recent[0])

        # Accumulation: tight range after decline, volume increasing
        if recent_range < older_range * 0.5 and avg_vol_recent > avg_vol_older * 0.8 and trend <= 0:
            return WyckoffPhase.ACCUMULATION.value

        # Distribution: tight range after rally, volume increasing
        if recent_range < older_range * 0.5 and avg_vol_recent > avg_vol_older * 0.8 and trend >= 0:
            return WyckoffPhase.DISTRIBUTION.value

        # Markup: expanding range upward
        if trend > 0 and recent_range > older_range:
            return WyckoffPhase.MARKUP.value

        # Markdown: expanding range downward
        if trend < 0 and recent_range > older_range:
            return WyckoffPhase.MARKDOWN.value

        return WyckoffPhase.UNKNOWN.value

    # ─── FUTURE-READY STUBS ──────────────────────────────────

    @staticmethod
    def volume_profile(df: pd.DataFrame) -> Dict:
        """FUTURE-READY: Volume Profile analysis."""
        # Requires tick-level or volume-at-price data
        return {"status": "not_implemented", "note": "Requires Level 2 data feed"}

    @staticmethod
    def footprint_analysis(df: pd.DataFrame) -> Dict:
        """FUTURE-READY: Footprint chart concepts."""
        return {"status": "not_implemented", "note": "Requires bid/ask volume data"}

    @staticmethod
    def delta_analysis(df: pd.DataFrame) -> Dict:
        """FUTURE-READY: Delta (buy vs sell volume) analysis."""
        return {"status": "not_implemented", "note": "Requires order flow data"}


# Singleton
smc_engine = SmartMoneyEngine()
