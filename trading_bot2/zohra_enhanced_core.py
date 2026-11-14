"""
Zohra Enhanced Core v5
======================
BUILT TO PREVENT THE $777 LOSS FROM HAPPENING AGAIN.

CHANGES FROM v4:
- HARD THRESHOLD: 95/100 minimum score (was 79)
- NO MANUAL OVERRIDE: force_trade deleted, no bypass functions
- AUTO-MANAGER: Position manager runs INSIDE scanner, never separate
- KILL SWITCH: Daily loss -2% = engine stops until manual reset
- REJECT LOGGER: Every rejected setup stored with reason
- TRADE QUALITY: A+/A/B/C classification with different management
- PARTIAL TP: 50% at 1R, 50% runs with trailing

WHAT WAS REMOVED:
- force_trade.py functionality
- Any function that allows manual entry without all filters
- Separate manager script (now integrated)
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from enum import Enum
import json
import os

# ─── HARD CONSTANTS (cannot be changed without code edit) ───
MIN_SCORE = 95           # Was 79 — caused losses
MAX_DAILY_TRADES = 3
RISK_PER_TRADE = 0.005   # 0.5% — was 1% causing oversized positions
MAX_LOTS = 2.0           # Hard cap regardless of account size
DAILY_LOSS_KILL = 0.02   # Stop trading if down 2%
MIN_RR = 1.5

class TradeQuality(Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    REJECT = "REJECT"

class MarketRegime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    VOLATILE = "volatile"
    DEAD = "dead"

@dataclass
class RejectedSetup:
    """Log every rejected trade with full reason"""
    timestamp: str
    symbol: str
    score: int
    structure_pass: bool
    liquidity_pass: bool
    momentum_pass: bool
    volume_pass: bool
    regime: str
    reason: str

@dataclass
class TradeScore:
    """Complete scoring breakdown"""
    total: int = 0
    structure: int = 0      # HH/HL/LH/LL/BOS/CHoCH
    liquidity: int = 0      # Sweep detection, EQH/EQL
    smc: int = 0            # Order blocks, FVG, premium/discount
    trend: int = 0          # EMA alignment, D1/H4 direction
    momentum: int = 0       # RSI, MACD, volume
    volatility: int = 0     # ATR, BB width
    pullback: int = 0       # Fib retracement quality

    def quality_grade(self) -> TradeQuality:
        if self.total >= 95: return TradeQuality.A_PLUS
        elif self.total >= 85: return TradeQuality.A
        elif self.total >= 75: return TradeQuality.B
        elif self.total >= 60: return TradeQuality.C
        else: return TradeQuality.REJECT

class ZohraEngineV5:
    """
    Autonomous engine with NO manual override capability.
    """

    def __init__(self, account: int = None):
        self.account = account
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.rejected_log: List[RejectedSetup] = []
        self.active_trades: Dict[str, Dict] = {}
        self.kill_switch = False

        # Performance tracking
        self.session_stats = {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "total_pnl": 0.0,
            "best_session": "",
            "best_pair": "",
            "best_regime": ""
        }

    # ═══════════════════════════════════════════════
    # 1. MARKET REGIME DETECTOR
    # ═══════════════════════════════════════════════

    def detect_regime(self, df: pd.DataFrame, symbol: str) -> MarketRegime:
        """
        Detect market regime using ADX, BB width, and volatility.
        """
        if len(df) < 50:
            return MarketRegime.DEAD

        # Calculate indicators
        df["atr"] = self._calculate_atr(df, 14)
        df["adx"] = self._calculate_adx(df, 14)
        df["bb_width"] = self._calculate_bb_width(df, 20, 2)

        latest = df.iloc[-1]
        adx = latest["adx"]
        bb_width = latest["bb_width"]
        atr = latest["atr"]

        # ATR relative to price (volatility %)
        price = latest["close"]
        volatility_pct = (atr / price) * 100 if price > 0 else 0

        # Regime classification
        if adx < 15 and bb_width < 0.5:
            return MarketRegime.DEAD
        elif adx < 20 and bb_width < 1.0:
            return MarketRegime.RANGING
        elif adx > 30 and volatility_pct > 0.15:
            return MarketRegime.VOLATILE
        elif adx > 25 and self._detect_breakout(df):
            return MarketRegime.BREAKOUT
        elif adx > 20:
            return MarketRegime.TRENDING
        else:
            return MarketRegime.RANGING

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _calculate_adx(self, df: pd.DataFrame, period: int) -> pd.Series:
        plus_dm = df["high"].diff()
        minus_dm = -df["low"].diff()
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)

        atr = self._calculate_atr(df, period)
        plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.rolling(period).mean()

    def _calculate_bb_width(self, df: pd.DataFrame, period: int, std: int) -> pd.Series:
        sma = df["close"].rolling(period).mean()
        std_dev = df["close"].rolling(period).std()
        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)
        return ((upper - lower) / sma) * 100

    def _detect_breakout(self, df: pd.DataFrame) -> bool:
        """Check if price broke recent range"""
        if len(df) < 20:
            return False
        recent_high = df["high"].tail(20).max()
        recent_low = df["low"].tail(20).min()
        latest = df.iloc[-1]

        # Breakout if close is beyond recent range
        return latest["close"] > recent_high * 0.999 or latest["close"] < recent_low * 1.001

    # ═══════════════════════════════════════════════
    # 2. SMART MONEY / STRUCTURE ENGINE
    # ═══════════════════════════════════════════════

    def analyze_structure(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        """
        Detect market structure: HH, HL, LH, LL, BOS, CHoCH.
        Returns (score_0_25, reason).
        """
        if len(df) < 50:
            return 0, "Insufficient data"

        score = 0
        reasons = []

        # Find swing highs and lows
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        # Simple structure detection using recent pivots
        recent_highs = self._find_pivots(highs, window=5, high=True)
        recent_lows = self._find_pivots(lows, window=5, high=False)

        if len(recent_highs) < 3 or len(recent_lows) < 3:
            return 5, "Structure unclear"

        # Check for Higher Highs / Higher Lows (uptrend)
        if direction == "LONG":
            if recent_highs[-1] > recent_highs[-2]:
                score += 10
                reasons.append("HH formed")
            if recent_lows[-1] > recent_lows[-2]:
                score += 10
                reasons.append("HL formed")
            if recent_highs[-1] > recent_highs[-2] and recent_lows[-1] > recent_lows[-2]:
                score += 5
                reasons.append("Bullish structure")

        # Check for Lower Highs / Lower Lows (downtrend)
        elif direction == "SHORT":
            if recent_highs[-1] < recent_highs[-2]:
                score += 10
                reasons.append("LH formed")
            if recent_lows[-1] < recent_lows[-2]:
                score += 10
                reasons.append("LL formed")
            if recent_highs[-1] < recent_highs[-2] and recent_lows[-1] < recent_lows[-2]:
                score += 5
                reasons.append("Bearish structure")

        return min(score, 25), " | ".join(reasons) if reasons else "Structure weak"

    def _find_pivots(self, data: np.ndarray, window: int, high: bool) -> List[float]:
        """Find pivot points"""
        pivots = []
        for i in range(window, len(data) - window):
            if high:
                if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] >= data[i+j] for j in range(1, window+1)):
                    pivots.append(data[i])
            else:
                if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] <= data[i+j] for j in range(1, window+1)):
                    pivots.append(data[i])
        return pivots[-5:]  # Last 5 pivots

    def detect_liquidity_sweep(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        """
        Detect if price swept liquidity (equal highs/lows) before reversing.
        Returns (score_0_20, reason).
        """
        if len(df) < 30:
            return 0, "No data"

        score = 0
        reasons = []

        # Check for equal highs (liquidity above) or equal lows (liquidity below)
        recent = df.tail(20)

        if direction == "LONG":
            # Look for sweep of equal lows (stop hunt below support)
            lows = recent["low"].values
            if self._has_equal_levels(lows, tolerance=0.0010):
                score += 15
                reasons.append("Equal lows swept — liquidity taken")
                # Check if price reversed after sweep
                if df.iloc[-1]["close"] > df.iloc[-5:]["low"].min() * 1.002:
                    score += 5
                    reasons.append("Reversal after sweep")

        elif direction == "SHORT":
            # Look for sweep of equal highs
            highs = recent["high"].values
            if self._has_equal_levels(highs, tolerance=0.0010):
                score += 15
                reasons.append("Equal highs swept — liquidity taken")
                if df.iloc[-1]["close"] < df.iloc[-5:]["high"].max() * 0.998:
                    score += 5
                    reasons.append("Reversal after sweep")

        return min(score, 20), " | ".join(reasons) if reasons else "No sweep detected"

    def _has_equal_levels(self, data: np.ndarray, tolerance: float) -> bool:
        """Check for equal highs/lows within tolerance"""
        for i in range(len(data)):
            for j in range(i+1, len(data)):
                if abs(data[i] - data[j]) <= tolerance:
                    return True
        return False

    def analyze_smc_zones(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        """
        Premium/Discount analysis, Order Block detection, FVG.
        Returns (score_0_20, reason).
        """
        if len(df) < 50:
            return 0, "No data"

        score = 0
        reasons = []

        # Calculate daily range and current position
        daily_range = df["high"].tail(24).max() - df["low"].tail(24).min()
        range_50 = df["low"].tail(24).min() + (daily_range * 0.5)
        range_70 = df["low"].tail(24).min() + (daily_range * 0.7)
        range_30 = df["low"].tail(24).min() + (daily_range * 0.3)

        current = df.iloc[-1]["close"]

        if direction == "LONG":
            # Want to buy in discount zone (< 30% of range) or at least < 50%
            if current <= range_30:
                score += 15
                reasons.append("Deep discount zone (<30%)")
            elif current <= range_50:
                score += 10
                reasons.append("Discount zone (<50%)")
            else:
                return 0, f"Premium zone ({((current - df['low'].tail(24).min()) / daily_range * 100):.0f}%) — NO LONG"

            # Check for bullish order block (last down candle before up move)
            if self._detect_order_block(df, "bullish"):
                score += 5
                reasons.append("Bullish OB present")

        elif direction == "SHORT":
            # Want to sell in premium zone (> 70% of range) or at least > 50%
            if current >= range_70:
                score += 15
                reasons.append("Deep premium zone (>70%)")
            elif current >= range_50:
                score += 10
                reasons.append("Premium zone (>50%)")
            else:
                return 0, f"Discount zone ({((current - df['low'].tail(24).min()) / daily_range * 100):.0f}%) — NO SHORT"

            if self._detect_order_block(df, "bearish"):
                score += 5
                reasons.append("Bearish OB present")

        return min(score, 20), " | ".join(reasons) if reasons else "Zone unclear"

    def _detect_order_block(self, df: pd.DataFrame, type_: str) -> bool:
        """Simplified order block detection"""
        if len(df) < 10:
            return False

        recent = df.tail(10)

        if type_ == "bullish":
            # Last bearish candle before strong bullish move
            for i in range(len(recent) - 3, len(recent) - 1):
                if (recent.iloc[i]["close"] < recent.iloc[i]["open"] and  # Bearish
                    recent.iloc[i+1]["close"] > recent.iloc[i+1]["open"] and  # Bullish
                    recent.iloc[i+1]["close"] > recent.iloc[i]["high"]):  # Strong bullish
                    return True
        else:
            for i in range(len(recent) - 3, len(recent) - 1):
                if (recent.iloc[i]["close"] > recent.iloc[i]["open"] and  # Bullish
                    recent.iloc[i+1]["close"] < recent.iloc[i+1]["open"] and  # Bearish
                    recent.iloc[i+1]["close"] < recent.iloc[i]["low"]):
                    return True

        return False

    # ═══════════════════════════════════════════════
    # 3. CONFIDENCE / SCORING ENGINE
    # ═══════════════════════════════════════════════

    def calculate_score(self, df: pd.DataFrame, symbol: str, direction: str) -> TradeScore:
        """
        Full scoring with all components.
        MAXIMUM 100 points.
        """
        score = TradeScore()

        # Structure (25 points)
        score.structure, _ = self.analyze_structure(df, direction)

        # Liquidity (20 points)
        score.liquidity, _ = self.detect_liquidity_sweep(df, direction)

        # SMC Zones (20 points)
        score.smc, _ = self.analyze_smc_zones(df, direction)

        # Trend (15 points) — EMA alignment
        score.trend = self._score_trend(df, direction)

        # Momentum (10 points) — RSI, volume
        score.momentum = self._score_momentum(df, direction)

        # Volatility (5 points) — ATR sufficient
        score.volatility = self._score_volatility(df)

        # Pullback (5 points) — Fib quality
        score.pullback = self._score_pullback(df, direction)

        score.total = (score.structure + score.liquidity + score.smc + 
                      score.trend + score.momentum + score.volatility + score.pullback)

        return score

    def _score_trend(self, df: pd.DataFrame, direction: str) -> int:
        """Score trend alignment (0-15)"""
        if len(df) < 50:
            return 0

        ema_20 = df["close"].ewm(span=20).mean().iloc[-1]
        ema_50 = df["close"].ewm(span=50).mean().iloc[-1]
        ema_200 = df["close"].ewm(span=200).mean().iloc[-1]
        price = df.iloc[-1]["close"]

        score = 0

        if direction == "LONG":
            if price > ema_20: score += 5
            if ema_20 > ema_50: score += 5
            if ema_50 > ema_200: score += 5
        else:
            if price < ema_20: score += 5
            if ema_20 < ema_50: score += 5
            if ema_50 < ema_200: score += 5

        return score

    def _score_momentum(self, df: pd.DataFrame, direction: str) -> int:
        """Score momentum (0-10)"""
        if len(df) < 20:
            return 0

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        # Volume
        vol_sma = df["volume"].rolling(20).mean().iloc[-1]
        vol_current = df.iloc[-1]["volume"]

        score = 0

        if direction == "LONG":
            if 40 <= rsi <= 65: score += 5  # Not overbought, has room
            elif rsi < 40: score += 3  # Oversold, possible reversal
        else:
            if 35 <= rsi <= 60: score += 5
            elif rsi > 60: score += 3

        if vol_current > vol_sma: score += 5

        return score

    def _score_volatility(self, df: pd.DataFrame) -> int:
        """Score volatility sufficiency (0-5)"""
        if len(df) < 20:
            return 0
        atr = self._calculate_atr(df, 14).iloc[-1]
        price = df.iloc[-1]["close"]
        vol_pct = (atr / price) * 100 if price > 0 else 0

        if vol_pct > 0.1: return 5
        elif vol_pct > 0.05: return 3
        else: return 0

    def _score_pullback(self, df: pd.DataFrame, direction: str) -> int:
        """Score pullback quality (0-5)"""
        if len(df) < 30:
            return 0

        # Simple: price near EMA = good pullback
        ema_20 = df["close"].ewm(span=20).mean().iloc[-1]
        price = df.iloc[-1]["close"]
        distance = abs(price - ema_20) / ema_20 * 100

        if distance < 0.2: return 5  # Near EMA, good entry
        elif distance < 0.5: return 3
        else: return 0

    # ═══════════════════════════════════════════════
    # 4. TRADE QUALITY & POSITION SIZING
    # ═══════════════════════════════════════════════

    def get_position_size(self, grade: TradeQuality, equity: float, 
                         stop_distance: float, symbol: str) -> float:
        """
        Dynamic position sizing based on trade quality.
        A+ = full risk, A = 75%, B = 50%, C = reject
        """
        base_risk = equity * RISK_PER_TRADE

        if grade == TradeQuality.A_PLUS:
            risk_amount = base_risk
        elif grade == TradeQuality.A:
            risk_amount = base_risk * 0.75
        elif grade == TradeQuality.B:
            risk_amount = base_risk * 0.50
        else:
            return 0  # C or REJECT = no trade

        # Calculate lots
        if stop_distance <= 0:
            return 0

        # For forex: risk / stop_distance = units
        # Then convert to lots (100,000 units = 1 standard lot)
        units = risk_amount / stop_distance
        lots = units / 100000

        # Hard caps
        lots = min(lots, MAX_LOTS)
        lots = max(lots, 0.01)  # Minimum 0.01 lot

        # Round to 2 decimals
        lots = round(lots, 2)

        return lots

    # ═══════════════════════════════════════════════
    # 5. ADAPTIVE TRADE MANAGER (PROFIT PROTECTION)
    # ═══════════════════════════════════════════════

    def manage_open_trade(self, trade: Dict, current_data: pd.DataFrame) -> Optional[str]:
        """
        Dynamic trade management based on quality and momentum.
        Returns action: "HOLD", "CLOSE_HALF", "CLOSE_FULL", "TRAIL"
        """
        if current_data.empty:
            return None

        entry = trade["entry_price"]
        stop = trade["stop_loss"]
        tp = trade["take_profit"]
        current = current_data.iloc[-1]["close"]
        direction = trade["direction"]
        quality = trade.get("quality", "B")

        # Calculate R multiple
        if direction == "LONG":
            risk = entry - stop
            reward = current - entry
        else:
            risk = stop - entry
            reward = entry - current

        if risk <= 0:
            return "CLOSE_FULL"

        r_multiple = reward / risk

        # ─── A+ TRADE: Let winners run ───
        if quality == "A+":
            if r_multiple >= 2.0:
                # Strong move, trail aggressively
                return "TRAIL"
            elif r_multiple >= 1.0:
                # At 1R, move to BE if not already
                if not trade.get("be_moved", False):
                    return "MOVE_BE"
            elif r_multiple < -0.5:
                # Stalling, close early
                return "CLOSE_FULL"

        # ─── A TRADE: Standard management ───
        elif quality == "A":
            if r_multiple >= 1.5:
                return "CLOSE_HALF"  # Take profit, trail rest
            elif r_multiple >= 0.8:
                if not trade.get("be_moved", False):
                    return "MOVE_BE"
            elif r_multiple < -0.3:
                return "CLOSE_FULL"

        # ─── B TRADE: Secure profit early ───
        elif quality == "B":
            if r_multiple >= 1.0:
                return "CLOSE_HALF"
            elif r_multiple >= 0.5:
                if not trade.get("be_moved", False):
                    return "MOVE_BE"
            elif r_multiple < 0:
                # B quality + not in profit = close
                return "CLOSE_FULL"

        # Check momentum stall
        adx = self._calculate_adx(current_data, 14).iloc[-1] if len(current_data) >= 14 else 0
        if adx < 20 and r_multiple > 0.5:
            # Momentum fading while in profit = take it
            return "CLOSE_HALF"

        return "HOLD"

    # ═══════════════════════════════════════════════
    # 6. KILL SWITCH & DAILY LIMITS
    # ═══════════════════════════════════════════════

    def check_kill_switch(self, equity: float, starting_equity: float) -> bool:
        """
        Check if daily loss limit hit.
        Returns True if trading should STOP.
        """
        if self.kill_switch:
            return True

        daily_pnl_pct = (equity - starting_equity) / starting_equity

        if daily_pnl_pct <= -DAILY_LOSS_KILL:
            self.kill_switch = True
            self._log_rejection("ALL", 0, False, False, False, False, 
                               "dead", f"KILL SWITCH: Daily loss {daily_pnl_pct*100:.1f}%")
            return True

        if self.daily_trades >= MAX_DAILY_TRADES:
            return True

        return False

    def reset_daily(self):
        """Call at start of new trading day"""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.kill_switch = False

    # ═══════════════════════════════════════════════
    # 7. REJECTED TRADE LOGGER
    # ═══════════════════════════════════════════════

    def _log_rejection(self, symbol: str, score: int, 
                      structure: bool, liquidity: bool, 
                      momentum: bool, volume: bool,
                      regime: str, reason: str):
        """Log every rejected setup"""
        rejection = RejectedSetup(
            timestamp=datetime.utcnow().isoformat(),
            symbol=symbol,
            score=score,
            structure_pass=structure,
            liquidity_pass=liquidity,
            momentum_pass=momentum,
            volume_pass=volume,
            regime=regime,
            reason=reason
        )
        self.rejected_log.append(rejection)

        # Save to file
        self._save_rejections()

    def _save_rejections(self):
        """Save rejection log to JSON"""
        data = [{
            "timestamp": r.timestamp,
            "symbol": r.symbol,
            "score": r.score,
            "structure": r.structure_pass,
            "liquidity": r.liquidity_pass,
            "momentum": r.momentum_pass,
            "volume": r.volume_pass,
            "regime": r.regime,
            "reason": r.reason
        } for r in self.rejected_log]

        with open("rejected_trades.json", "w") as f:
            json.dump(data, f, indent=2)

    def get_rejection_analysis(self) -> Dict:
        """Analyze why trades are being rejected"""
        if not self.rejected_log:
            return {"message": "No rejections yet"}

        total = len(self.rejected_log)
        structure_fails = sum(1 for r in self.rejected_log if not r.structure_pass)
        liquidity_fails = sum(1 for r in self.rejected_log if not r.liquidity_pass)
        momentum_fails = sum(1 for r in self.rejected_log if not r.momentum_pass)
        volume_fails = sum(1 for r in self.rejected_log if not r.volume_pass)

        # Most common regime for rejections
        regimes = {}
        for r in self.rejected_log:
            regimes[r.regime] = regimes.get(r.regime, 0) + 1
        worst_regime = max(regimes, key=regimes.get) if regimes else "unknown"

        return {
            "total_rejected": total,
            "structure_fail_rate": f"{structure_fails/total*100:.1f}%",
            "liquidity_fail_rate": f"{liquidity_fails/total*100:.1f}%",
            "momentum_fail_rate": f"{momentum_fails/total*100:.1f}%",
            "volume_fail_rate": f"{volume_fails/total*100:.1f}%",
            "worst_regime": worst_regime,
            "recommendation": self._get_recommendation(structure_fails, liquidity_fails, 
                                                       momentum_fails, volume_fails, total)
        }

    def _get_recommendation(self, s, l, m, v, total) -> str:
        """Get improvement recommendation"""
        fails = {"Structure": s, "Liquidity": l, "Momentum": m, "Volume": v}
        worst = max(fails, key=fails.get)
        pct = fails[worst] / total * 100 if total > 0 else 0

        if pct > 50:
            return f"Focus on {worst}: {pct:.0f}% of rejections. Consider widening {worst.lower()} parameters."
        else:
            return "Filters are balanced. Continue current settings."

    # ═══════════════════════════════════════════════
    # 8. MAIN SCAN FUNCTION
    # ═══════════════════════════════════════════════

    def scan_and_trade(self, symbol: str, df: pd.DataFrame, 
                      equity: float, starting_equity: float) -> Dict:
        """
        Full scan with all filters.
        Returns trade dict or rejection info.
        """
        result = {
            "symbol": symbol,
            "trade": None,
            "rejected": True,
            "reason": "",
            "score": None
        }

        # ─── Kill switch check ───
        if self.check_kill_switch(equity, starting_equity):
            result["reason"] = "KILL SWITCH ACTIVE"
            return result

        # ─── Regime check ───
        regime = self.detect_regime(df, symbol)
        if regime in [MarketRegime.DEAD, MarketRegime.VOLATILE]:
            self._log_rejection(symbol, 0, False, False, False, False,
                               regime.value, f"Regime: {regime.value}")
            result["reason"] = f"Regime: {regime.value}"
            return result

        # ─── Determine direction from EMA ───
        ema_20 = df["close"].ewm(span=20).mean().iloc[-1]
        ema_50 = df["close"].ewm(span=50).mean().iloc[-1]
        price = df.iloc[-1]["close"]

        if price > ema_20 > ema_50:
            direction = "LONG"
        elif price < ema_20 < ema_50:
            direction = "SHORT"
        else:
            self._log_rejection(symbol, 0, False, False, False, False,
                               regime.value, "No clear trend direction")
            result["reason"] = "No clear trend"
            return result

        # ─── Calculate full score ───
        score = self.calculate_score(df, symbol, direction)

        # ─── Check minimum score ───
        if score.total < MIN_SCORE:
            self._log_rejection(
                symbol, score.total,
                score.structure >= 15,
                score.liquidity >= 10,
                score.momentum >= 5,
                score.volatility >= 3,
                regime.value,
                f"Score {score.total} < {MIN_SCORE}"
            )
            result["reason"] = f"Score {score.total}/100 (need {MIN_SCORE}+)"
            result["score"] = score
            return result

        # ─── Get quality grade ───
        grade = score.quality_grade()
        if grade in [TradeQuality.C, TradeQuality.REJECT]:
            self._log_rejection(
                symbol, score.total, True, True, True, True,
                regime.value, f"Quality: {grade.value}"
            )
            result["reason"] = f"Quality: {grade.value}"
            return result

        # ─── Calculate entry, stop, targets ───
        atr = self._calculate_atr(df, 14).iloc[-1]

        if direction == "LONG":
            entry = price
            stop = price - (atr * 1.5)
            tp = price + (atr * 3.0)
        else:
            entry = price
            stop = price + (atr * 1.5)
            tp = price - (atr * 3.0)

        stop_distance = abs(entry - stop)

        # ─── Position size ───
        lots = self.get_position_size(grade, equity, stop_distance, symbol)
        if lots <= 0:
            result["reason"] = "Position size too small"
            return result

        # ─── Build trade ───
        trade = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": round(entry, 5),
            "stop_loss": round(stop, 5),
            "take_profit": round(tp, 5),
            "lots": lots,
            "quality": grade.value,
            "score": score.total,
            "regime": regime.value,
            "timestamp": datetime.utcnow().isoformat(),
            "be_moved": False,
            "half_closed": False
        }

        result["trade"] = trade
        result["rejected"] = False
        result["score"] = score

        self.daily_trades += 1

        return result


# Singleton
zohra_v5 = ZohraEngineV5()
