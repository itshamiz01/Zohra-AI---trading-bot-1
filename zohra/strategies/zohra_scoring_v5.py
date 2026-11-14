"""
Zohra Scoring Engine v5 — extracted from trading_bot2/zohra_enhanced_core.py
Pure MT5-agnostic SMC scoring. No broker references.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from zohra.core.enums import MarketRegime, TradeQuality, StrategyName
from zohra.strategies.base import BaseStrategy


MIN_SCORE = 75
MIN_RR = 1.5


@dataclass
class TradeScore:
    total: int = 0
    structure: int = 0
    liquidity: int = 0
    smc: int = 0
    trend: int = 0
    momentum: int = 0
    volatility: int = 0
    pullback: int = 0
    reasons: List[str] = None

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []

    def quality_grade(self) -> TradeQuality:
        if self.total >= 95:
            return TradeQuality.A_PLUS
        if self.total >= 85:
            return TradeQuality.A
        if self.total >= 75:
            return TradeQuality.B
        if self.total >= 60:
            return TradeQuality.C
        return TradeQuality.REJECT

    def failed_conditions(self) -> List[str]:
        failed = []
        if self.structure < 15:
            failed.append("structure")
        if self.liquidity < 10:
            failed.append("liquidity")
        if self.smc < 10:
            failed.append("smc")
        if self.trend < 10:
            failed.append("trend")
        if self.momentum < 10:
            failed.append("momentum")
        if self.volatility < 5:
            failed.append("volatility")
        if self.total < MIN_SCORE:
            failed.append(f"score_below_{MIN_SCORE}")
        return failed

    def to_dict(self) -> Dict:
        return {
            "total": self.total,
            "structure": self.structure,
            "liquidity": self.liquidity,
            "smc": self.smc,
            "trend": self.trend,
            "momentum": self.momentum,
            "volatility": self.volatility,
            "pullback": self.pullback,
            "quality": self.quality_grade().value,
            "reasons": self.reasons,
        }


class ZohraScoringEngine(BaseStrategy):
    """SMC confluence scorer with regime detection and rejection diagnostics."""

    @classmethod
    def metadata(cls):
        """Structured metadata for the Strategy Registry (Phase 2)."""
        return {
            "name": "zohra_v5",
            "category": "SMC",
            "applicable_regimes": ["trending", "ranging", "volatile", "breakout"],
            "applicable_sessions": ["London", "NewYork", "Asian", "Overlap"],
            "applicable_timeframes": ["M5", "M15", "H1", "H4", "D1"],
            "min_rrr": 1.5,
            "description": "SMC confluence scoring engine measuring structure, liquidity, trend, and volume."
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return None

        for direction in ["LONG", "SHORT"]:
            approved, score, reason = self.evaluate(df, direction)
            if approved:
                latest = df.iloc[-1]
                price = latest["close"]
                atr = self._atr(df, 14).iloc[-1]
                
                # Determine SL & TP levels
                if direction == "LONG":
                    stop = price - atr * 1.5
                    tp = price + atr * 3.0
                else:
                    stop = price + atr * 1.5
                    tp = price - atr * 3.0
                    
                return {
                    "strategy": StrategyName.ZOHRA_V5.value,
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": price,
                    "stop_loss": round(stop, 5),
                    "take_profit": round(tp, 5),
                    "reason": reason,
                    "indicators": {
                        "score": score.total,
                        "structure": score.structure,
                        "liquidity": score.liquidity,
                        "smc": score.smc,
                        "trend": score.trend,
                        "momentum": score.momentum,
                        "volatility": score.volatility
                    }
                }
        return None

    def detect_regime(self, df: pd.DataFrame) -> MarketRegime:
        if len(df) < 50:
            return MarketRegime.LOW_LIQUIDITY
        df = df.copy()
        df["atr"] = self._atr(df, 14)
        df["adx"] = self._adx(df, 14)
        latest = df.iloc[-1]
        adx = latest["adx"]
        price = latest["close"]
        vol_pct = (latest["atr"] / price) * 100 if price > 0 else 0

        if adx < 15:
            return MarketRegime.LOW_LIQUIDITY
        if adx < 20:
            return MarketRegime.RANGING
        if adx > 30 and vol_pct > 0.15:
            return MarketRegime.HIGH_VOLATILITY
        if adx > 25:
            return MarketRegime.TRENDING
        return MarketRegime.RANGING

    def score_setup(self, df: pd.DataFrame, direction: str) -> TradeScore:
        score = TradeScore()
        s, r = self._analyze_structure(df, direction)
        score.structure, score.reasons = s, score.reasons + [r]
        l, r = self._detect_liquidity_sweep(df, direction)
        score.liquidity = l
        score.reasons.append(r)
        z, r = self._analyze_smc_zones(df, direction)
        score.smc = z
        score.reasons.append(r)
        t, r = self._analyze_trend(df, direction)
        score.trend = t
        score.reasons.append(r)
        m, r = self._analyze_momentum(df, direction)
        score.momentum = m
        score.reasons.append(r)
        v, r = self._analyze_volatility(df)
        score.volatility = v
        score.reasons.append(r)
        score.total = min(
            score.structure + score.liquidity + score.smc + score.trend + score.momentum + score.volatility,
            100,
        )
        return score

    def evaluate(self, df: pd.DataFrame, direction: str, min_score: int = MIN_SCORE) -> Tuple[bool, TradeScore, str]:
        regime = self.detect_regime(df)
        if regime == MarketRegime.LOW_LIQUIDITY:
            return False, TradeScore(), "Market regime LOW_LIQUIDITY — no trade"
        score = self.score_setup(df, direction)
        if score.total < min_score:
            return False, score, f"Score {score.total}/{min_score} insufficient"
        return True, score, f"Approved score={score.total} quality={score.quality_grade().value}"

    def _analyze_structure(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        if len(df) < 50:
            return 0, "Insufficient data"
        highs = self._find_pivots(df["high"].values, 5, True)
        lows = self._find_pivots(df["low"].values, 5, False)
        if len(highs) < 2 or len(lows) < 2:
            return 5, "Structure unclear"
        score, reasons = 0, []
        if direction == "LONG":
            if highs[-1] > highs[-2]:
                score += 10
                reasons.append("HH")
            if lows[-1] > lows[-2]:
                score += 10
                reasons.append("HL")
        else:
            if highs[-1] < highs[-2]:
                score += 10
                reasons.append("LH")
            if lows[-1] < lows[-2]:
                score += 10
                reasons.append("LL")
        return min(score, 25), " | ".join(reasons) or "weak structure"

    def _detect_liquidity_sweep(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        recent = df.tail(20)
        score = 0
        if direction == "LONG" and self._equal_levels(recent["low"].values):
            score = 15
            if df.iloc[-1]["close"] > recent["low"].min() * 1.002:
                score += 5
            return score, "Liquidity sweep (lows)"
        if direction == "SHORT" and self._equal_levels(recent["high"].values):
            score = 15
            if df.iloc[-1]["close"] < recent["high"].max() * 0.998:
                score += 5
            return score, "Liquidity sweep (highs)"
        return 0, "No sweep"

    def _analyze_smc_zones(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        dr = df["high"].tail(24).max() - df["low"].tail(24).min()
        if dr <= 0:
            return 0, "No range"
        lo = df["low"].tail(24).min()
        current = df.iloc[-1]["close"]
        pct = (current - lo) / dr * 100
        if direction == "LONG":
            if pct <= 30:
                return 15, "Deep discount"
            if pct <= 50:
                return 10, "Discount zone"
            return 0, f"Premium zone ({pct:.0f}%) — no long"
        if pct >= 70:
            return 15, "Deep premium"
        if pct >= 50:
            return 10, "Premium zone"
        return 0, f"Discount zone ({pct:.0f}%) — no short"

    def _analyze_trend(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        df = df.copy()
        df["ema20"] = df["close"].ewm(span=20).mean()
        df["ema50"] = df["close"].ewm(span=50).mean()
        latest = df.iloc[-1]
        if direction == "LONG" and latest["close"] > latest["ema20"] > latest["ema50"]:
            return 15, "Bullish EMA stack"
        if direction == "SHORT" and latest["close"] < latest["ema20"] < latest["ema50"]:
            return 15, "Bearish EMA stack"
        return 5, "Trend weak"

    def _analyze_momentum(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        if direction == "LONG" and 40 < val < 70:
            return 15, f"RSI {val:.0f} bullish"
        if direction == "SHORT" and 30 < val < 60:
            return 15, f"RSI {val:.0f} bearish"
        return 5, f"RSI {val:.0f} neutral"

    def _analyze_volatility(self, df: pd.DataFrame) -> Tuple[int, str]:
        atr = self._atr(df, 14).iloc[-1]
        price = df.iloc[-1]["close"]
        pct = (atr / price) * 100 if price else 0
        if 0.05 < pct < 0.5:
            return 10, f"ATR {pct:.2f}%"
        return 3, f"ATR {pct:.2f}% out of range"

    @staticmethod
    def _atr(df: pd.DataFrame, period: int) -> pd.Series:
        hl = df["high"] - df["low"]
        hc = abs(df["high"] - df["close"].shift())
        lc = abs(df["low"] - df["close"].shift())
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _adx(df: pd.DataFrame, period: int) -> pd.Series:
        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        atr = ZohraScoringEngine._atr(df, period)
        plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.rolling(period).mean()

    @staticmethod
    def _find_pivots(data: np.ndarray, window: int, high: bool) -> List[float]:
        pivots = []
        for i in range(window, len(data) - window):
            if high:
                if all(data[i] >= data[i - j] for j in range(1, window + 1)) and all(
                    data[i] >= data[i + j] for j in range(1, window + 1)
                ):
                    pivots.append(data[i])
            else:
                if all(data[i] <= data[i - j] for j in range(1, window + 1)) and all(
                    data[i] <= data[i + j] for j in range(1, window + 1)
                ):
                    pivots.append(data[i])
        return pivots[-5:]

    @staticmethod
    def _equal_levels(data: np.ndarray, tol: float = 0.001) -> bool:
        for i in range(len(data)):
            for j in range(i + 1, len(data)):
                if abs(data[i] - data[j]) <= tol:
                    return True
        return False
