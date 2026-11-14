"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — SIGNAL SCORING ENGINE                ║
║  100-Point Scoring + Dynamic Quality Grading         ║
║  Adaptive Position Sizing & Risk Allocation          ║
╚══════════════════════════════════════════════════════╝

Score Breakdown (100 pts total):
  Structure   25 pts  — HH/HL/LH/LL, BOS, CHoCH
  Liquidity   20 pts  — Sweep detection, EQH/EQL
  SMC Zones   20 pts  — Order blocks, FVG, premium/discount
  Trend       15 pts  — EMA alignment (M15 + H1 + H4)
  Momentum    10 pts  — RSI, MACD, volume
  Volatility   5 pts  — ATR sufficient
  Pullback     5 pts  — Fibonacci quality

Dynamic Trade Classification System:
  A+ (90-100) → Elite Institutional    → 100% risk (1.00R), EXECUTE
  A  (80-89)  → High Probability       →  75% risk (0.75R), EXECUTE
  B  (70-79)  → Good Opportunity       →  50% risk (0.50R), EXECUTE
  C  (60-69)  → Speculative            →  25% risk (0.25R), OPTIONAL
  REJECT (<60)→ Low Quality             →   0% risk (0.00R), REJECT

Drawdown Adaptation:
  0-2%  DD → Normal risk
  2-4%  DD → Reduce by 25%
  4-6%  DD → Reduce by 50%
  6-8%  DD → Reduce by 75%
  >8%   DD → TRADING PAUSE
"""

import json
import os
import logging
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger("zohra.scorer")


# ════════════════════════════════════════════════
#  ENUMS & DATA CLASSES
# ════════════════════════════════════════════════

from zohra.core.enums import TradeQuality


@dataclass
class TradeScore:
    """Full scoring breakdown for one signal evaluation."""
    total:      int = 0
    structure:  int = 0   # HH/HL/LH/LL/BOS/CHoCH       — max 25
    liquidity:  int = 0   # Sweep, equal highs/lows       — max 20
    smc:        int = 0   # Order Blocks, FVG, zones      — max 20
    trend:      int = 0   # EMA alignment                 — max 15
    momentum:   int = 0   # RSI, MACD, volume             — max 10
    volatility: int = 0   # ATR sufficiency               — max 5
    pullback:   int = 0   # Fib pullback quality          — max 5

    # Human-readable reasons per module
    reasons: Dict[str, str] = field(default_factory=dict)

    def quality_grade(self) -> TradeQuality:
        if   self.total >= 90: return TradeQuality.A_PLUS
        elif self.total >= 80: return TradeQuality.A
        elif self.total >= 70: return TradeQuality.B
        elif self.total >= 60: return TradeQuality.C
        else:                  return TradeQuality.REJECT

    def to_dict(self) -> dict:
        d = asdict(self)
        d['grade'] = self.quality_grade().value
        return d

    def summary(self) -> str:
        return (
            f"Score={self.total}/100 Grade={self.quality_grade().value} | "
            f"Struct={self.structure} Liq={self.liquidity} SMC={self.smc} "
            f"Trend={self.trend} Mom={self.momentum} Vol={self.volatility} PB={self.pullback}"
        )


# ════════════════════════════════════════════════
#  KILL SWITCH STATE
# ════════════════════════════════════════════════

@dataclass
class KillSwitchState:
    active:       bool  = False
    daily_trades: int   = 0
    daily_pnl:    float = 0.0
    reason:       str   = ""


# ════════════════════════════════════════════════
#  SIGNAL SCORER CLASS
# ════════════════════════════════════════════════

class SignalScorer:
    """
    Production-grade signal evaluation engine.

    Input:  pandas DataFrame with OHLCV + indicators
    Output: TradeScore with grade and reasons

    Designed to be broker-agnostic — no MT5 imports.
    The calling code provides the DataFrame.
    """

    def __init__(self, min_score: int = 65, max_daily_trades: int = 10,
                 daily_loss_kill_pct: float = 0.02, max_lots: float = 2.0,
                 risk_per_trade: float = 0.005):
        self.min_score           = min_score
        self.max_daily_trades    = max_daily_trades
        self.daily_loss_kill_pct = daily_loss_kill_pct
        self.max_lots            = max_lots
        self.risk_per_trade      = risk_per_trade

        self._kill = KillSwitchState()

    # ─── Kill Switch ───────────────────────────────────────

    def check_kill_switch(self, equity: float, starting_equity: float) -> Tuple[bool, str]:
        """Returns (blocked, reason). True = cannot trade."""
        if self._kill.active:
            return True, f"Kill switch active: {self._kill.reason}"
        if starting_equity > 0 and equity > 0:
            pnl_pct = (equity - starting_equity) / starting_equity
            if pnl_pct <= -self.daily_loss_kill_pct:
                self._kill.active = True
                self._kill.reason = f"Daily loss {pnl_pct*100:.1f}% exceeded {self.daily_loss_kill_pct*100:.1f}% limit"
                logger.critical(f"🛑 KILL SWITCH ACTIVATED: {self._kill.reason}")
                return True, self._kill.reason
        if self._kill.daily_trades >= self.max_daily_trades:
            return True, f"Daily trade limit {self.max_daily_trades} reached"
        return False, ""

    def reset_daily(self):
        self._kill = KillSwitchState()
        logger.info("🌅 Kill switch + daily counters reset")

    def record_trade(self, pnl: float = 0.0):
        self._kill.daily_trades += 1
        self._kill.daily_pnl   += pnl

    @property
    def kill_switch_active(self) -> bool:
        return self._kill.active

    @property
    def daily_trades(self) -> int:
        return self._kill.daily_trades

    # ─── Pivot Detection ───────────────────────────────────

    def _find_pivots(self, data: np.ndarray, window: int = 5, high: bool = True) -> List[float]:
        pivots = []
        for i in range(window, len(data) - window):
            if high:
                if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] >= data[i+j] for j in range(1, window+1)):
                    pivots.append(float(data[i]))
            else:
                if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] <= data[i+j] for j in range(1, window+1)):
                    pivots.append(float(data[i]))
        return pivots[-8:]

    def _has_equal_levels(self, data: np.ndarray, tolerance_pct: float = 0.001) -> bool:
        price_ref = data.mean() if len(data) > 0 else 1.0
        tol = price_ref * tolerance_pct
        for i in range(len(data)):
            for j in range(i+1, len(data)):
                if abs(data[i] - data[j]) <= tol:
                    return True
        return False

    # ─── MODULE 1: Structure (max 25) ─────────────────────

    def _score_structure(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        if len(df) < 50:
            return 0, "Insufficient data"

        score, reasons = 0, []
        highs = df['high'].values
        lows  = df['low'].values

        recent_highs = self._find_pivots(highs, window=5, high=True)
        recent_lows  = self._find_pivots(lows,  window=5, high=False)

        if len(recent_highs) < 3 or len(recent_lows) < 3:
            return 5, "Structure unclear"

        if direction == "LONG":
            if recent_highs[-1] > recent_highs[-2]:
                score += 10; reasons.append("HH formed")
            if recent_lows[-1] > recent_lows[-2]:
                score += 10; reasons.append("HL formed")
            if score >= 20:
                score += 5;  reasons.append("Full bullish structure")

        elif direction == "SHORT":
            if recent_highs[-1] < recent_highs[-2]:
                score += 10; reasons.append("LH formed")
            if recent_lows[-1] < recent_lows[-2]:
                score += 10; reasons.append("LL formed")
            if score >= 20:
                score += 5;  reasons.append("Full bearish structure")

        return min(score, 25), " | ".join(reasons) if reasons else "Structure weak"

    # ─── MODULE 2: Liquidity (max 20) ─────────────────────

    def _score_liquidity(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        if len(df) < 30:
            return 0, "No data"

        score, reasons = 0, []
        recent = df.tail(20)

        if direction == "LONG":
            lows = recent['low'].values
            if self._has_equal_levels(lows):
                score += 15; reasons.append("Equal lows swept — liquidity taken")
                if df.iloc[-1]['close'] > df.iloc[-5:]['low'].min() * 1.002:
                    score += 5; reasons.append("Reversal after sweep")

        elif direction == "SHORT":
            highs = recent['high'].values
            if self._has_equal_levels(highs):
                score += 15; reasons.append("Equal highs swept — liquidity taken")
                if df.iloc[-1]['close'] < df.iloc[-5:]['high'].max() * 0.998:
                    score += 5; reasons.append("Reversal after sweep")

        return min(score, 20), " | ".join(reasons) if reasons else "No sweep detected"

    # ─── MODULE 3: SMC Zones (max 20) ─────────────────────

    def _score_smc_zones(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        if len(df) < 50:
            return 0, "No data"

        score, reasons = 0, []

        # Premium/Discount analysis (24-bar range = ~1 day on H1)
        lookback = min(24, len(df) - 1)
        daily_high = df['high'].tail(lookback).max()
        daily_low  = df['low'].tail(lookback).min()
        daily_rng  = daily_high - daily_low

        if daily_rng == 0:
            return 0, "Zero range"

        current   = df.iloc[-1]['close']
        pct_range = (current - daily_low) / daily_rng

        # Order block detection
        def has_order_block(df: pd.DataFrame, bull: bool) -> bool:
            recent = df.tail(10)
            for i in range(len(recent) - 3, len(recent) - 1):
                if bull:
                    if (recent.iloc[i]['close']   < recent.iloc[i]['open'] and
                        recent.iloc[i+1]['close'] > recent.iloc[i+1]['open'] and
                        recent.iloc[i+1]['close'] > recent.iloc[i]['high']):
                        return True
                else:
                    if (recent.iloc[i]['close']   > recent.iloc[i]['open'] and
                        recent.iloc[i+1]['close'] < recent.iloc[i+1]['open'] and
                        recent.iloc[i+1]['close'] < recent.iloc[i]['low']):
                        return True
            return False

        if direction == "LONG":
            if pct_range <= 0.30:
                score += 15; reasons.append(f"Deep discount ({pct_range*100:.0f}%)")
            elif pct_range <= 0.50:
                score += 10; reasons.append(f"Discount zone ({pct_range*100:.0f}%)")
            else:
                return 0, f"Premium zone ({pct_range*100:.0f}%) — skip LONG"
            if has_order_block(df, bull=True):
                score += 5; reasons.append("Bullish OB present")

        elif direction == "SHORT":
            if pct_range >= 0.70:
                score += 15; reasons.append(f"Deep premium ({pct_range*100:.0f}%)")
            elif pct_range >= 0.50:
                score += 10; reasons.append(f"Premium zone ({pct_range*100:.0f}%)")
            else:
                return 0, f"Discount zone ({pct_range*100:.0f}%) — skip SHORT"
            if has_order_block(df, bull=False):
                score += 5; reasons.append("Bearish OB present")

        return min(score, 20), " | ".join(reasons)

    # ─── MODULE 4: Trend (max 15) ─────────────────────────

    def _score_trend(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        if len(df) < 50:
            return 0, "No data"

        score, reasons = 0, []
        ema20  = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50  = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = df['close'].ewm(span=200, adjust=False).mean().iloc[-1] if len(df) >= 200 else ema50
        price  = df.iloc[-1]['close']

        if direction == "LONG":
            if price  > ema20:  score += 5;  reasons.append("Price > EMA20")
            if ema20  > ema50:  score += 5;  reasons.append("EMA20 > EMA50")
            if ema50  > ema200: score += 5;  reasons.append("EMA50 > EMA200")
        else:
            if price  < ema20:  score += 5;  reasons.append("Price < EMA20")
            if ema20  < ema50:  score += 5;  reasons.append("EMA20 < EMA50")
            if ema50  < ema200: score += 5;  reasons.append("EMA50 < EMA200")

        return score, " | ".join(reasons) if reasons else "Counter-trend"

    # ─── MODULE 5: Momentum (max 10) ──────────────────────

    def _score_momentum(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        if len(df) < 20:
            return 0, "No data"

        score, reasons = 0, []

        # RSI
        delta = df['close'].diff()
        gain  = delta.where(delta > 0, 0).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi   = (100 - (100 / (1 + gain / (loss + 1e-9)))).iloc[-1]

        # Volume
        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'
        if vol_col in df.columns:
            vol_sma = df[vol_col].rolling(20).mean().iloc[-1]
            vol_now = df[vol_col].iloc[-1]
            if vol_now > vol_sma:
                score += 5; reasons.append(f"Vol spike (×{vol_now/(vol_sma+1e-9):.1f})")

        if direction == "LONG":
            if 40 <= rsi <= 65:
                score += 5; reasons.append(f"RSI={rsi:.0f} (room to run)")
            elif rsi < 40:
                score += 3; reasons.append(f"RSI={rsi:.0f} (oversold)")
        else:
            if 35 <= rsi <= 60:
                score += 5; reasons.append(f"RSI={rsi:.0f} (room to fall)")
            elif rsi > 60:
                score += 3; reasons.append(f"RSI={rsi:.0f} (overbought)")

        return min(score, 10), " | ".join(reasons) if reasons else "Momentum weak"

    # ─── MODULE 6: Volatility (max 5) ─────────────────────

    def _score_volatility(self, df: pd.DataFrame) -> Tuple[int, str]:
        if len(df) < 20:
            return 0, "No data"
        high_low   = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close  = (df['low']  - df['close'].shift(1)).abs()
        atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1]
        price = df.iloc[-1]['close']
        vol_pct = (atr / price) * 100 if price > 0 else 0

        if vol_pct > 0.10:   return 5, f"ATR={atr:.5f} ({vol_pct:.3f}%) — sufficient"
        elif vol_pct > 0.05: return 3, f"ATR={atr:.5f} ({vol_pct:.3f}%) — borderline"
        else:                return 0, f"ATR={atr:.5f} ({vol_pct:.3f}%) — too low"

    # ─── MODULE 7: Pullback Quality (max 5) ───────────────

    def _score_pullback(self, df: pd.DataFrame, direction: str) -> Tuple[int, str]:
        if len(df) < 30:
            return 0, "No data"
        ema20    = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        price    = df.iloc[-1]['close']
        distance = abs(price - ema20) / (ema20 + 1e-9) * 100

        if distance < 0.2:   return 5, f"Near EMA ({distance:.2f}%) — clean pullback"
        elif distance < 0.5: return 3, f"Near EMA ({distance:.2f}%) — acceptable"
        else:                return 0, f"Far from EMA ({distance:.2f}%) — extended"

    # ─── MASTER SCORER ─────────────────────────────────────

    def calculate_score(self, df: pd.DataFrame, direction: str,
                        symbol: str = "") -> TradeScore:
        """
        Full 100-point signal evaluation.
        Call for each direction (LONG/SHORT) separately.
        """
        score = TradeScore()

        s1, r1 = self._score_structure(df, direction)
        s2, r2 = self._score_liquidity(df, direction)
        s3, r3 = self._score_smc_zones(df, direction)
        s4, r4 = self._score_trend(df, direction)
        s5, r5 = self._score_momentum(df, direction)
        s6, r6 = self._score_volatility(df)
        s7, r7 = self._score_pullback(df, direction)

        score.structure  = s1
        score.liquidity  = s2
        score.smc        = s3
        score.trend      = s4
        score.momentum   = s5
        score.volatility = s6
        score.pullback   = s7
        score.total      = s1 + s2 + s3 + s4 + s5 + s6 + s7

        score.reasons = {
            "Structure":  r1, "Liquidity":  r2, "SMC":       r3,
            "Trend":      r4, "Momentum":   r5, "Volatility": r6,
            "Pullback":   r7,
        }

        return score

    # ─── TRADE CLASSIFICATION ENGINE ──────────────────────

    def classify_setup(self, score: int) -> dict:
        """
        Classifies a trade setup into an institutional-grade quality tier.
        Returns a rich classification dict with grade, description, risk params,
        and execution action.

        Example output:
            {
                "grade": "A",
                "classification": "High Probability Opportunity",
                "position_mult": 0.75,
                "risk_r": "0.75R",
                "priority": "HIGH",
                "action": "EXECUTE",
                "confidence_pct": 87
            }
        """
        from zohra.config.settings import TRADE_CLASSIFICATION

        for grade_key, config in TRADE_CLASSIFICATION.items():
            if config["min_score"] <= score <= config["max_score"]:
                return {
                    "grade": grade_key,
                    "classification": config["classification"],
                    "position_mult": config["position_mult"],
                    "risk_r": f"{config['risk_r']:.2f}R",
                    "risk_r_numeric": config["risk_r"],
                    "priority": config["priority"],
                    "action": config["action"],
                    "confidence_pct": score,
                }

        # Fallback for scores outside all ranges (should not happen)
        return {
            "grade": "REJECT",
            "classification": "Low Quality — Rejected",
            "position_mult": 0.0,
            "risk_r": "0.00R",
            "risk_r_numeric": 0.0,
            "priority": "NONE",
            "action": "REJECT",
            "confidence_pct": score,
        }

    def get_drawdown_multiplier(self, drawdown_pct: float) -> float:
        """
        Returns the drawdown-adjusted risk multiplier from the settings config.
        Uses graduated scaling: as drawdown increases, risk is automatically reduced.
        """
        from zohra.config.settings import DRAWDOWN_RISK_SCALING, TRADING_PAUSE_DRAWDOWN_PCT

        if drawdown_pct >= TRADING_PAUSE_DRAWDOWN_PCT:
            return 0.0

        dd_mult = 1.0
        for threshold in sorted(DRAWDOWN_RISK_SCALING.keys()):
            if drawdown_pct <= threshold:
                dd_mult = DRAWDOWN_RISK_SCALING[threshold]
                break
        else:
            dd_mult = 0.25  # Fallback if above all thresholds but below pause

        return dd_mult

    def get_position_size(self, grade: TradeQuality, equity: float,
                          stop_distance: float, symbol: str = "EURUSD",
                          drawdown_pct: float = 0.0) -> float:
        """
        Dynamic lot sizing based on trade quality and account drawdown.

        Position Size = (Equity × BaseRisk × GradeMultiplier × DrawdownMultiplier) / (StopDistance × ContractSize)

        Grade Multipliers (from TRADE_CLASSIFICATION config):
          A+ → 100% of risk (1.00R)
          A  →  75% of risk (0.75R)
          B  →  50% of risk (0.50R)
          C  →  25% of risk (0.25R)

        Drawdown Adaptation (from DRAWDOWN_RISK_SCALING config):
          0-2%  → Normal risk (1.00)
          2-4%  → Reduce by 25% (0.75)
          4-6%  → Reduce by 50% (0.50)
          6-8%  → Reduce by 75% (0.25)
          >8%   → Trading Pause (0.00)
        """
        if stop_distance <= 0:
            return 0.0

        # Contract size lookup
        contract_size = 100000.0
        if symbol:
            try:
                from zohra.core.symbol_manager import symbol_manager
                params = symbol_manager.get_symbol_params(symbol)
                if params:
                    contract_size = params.get("contract_size", 100000.0)
                else:
                    if symbol == "XAUUSD":
                        contract_size = 100.0
                    elif symbol == "XAGUSD":
                        contract_size = 5000.0
                    elif "JPY" in symbol:
                        contract_size = 1000.0
                    elif symbol in ("US100", "SPX500"):
                        contract_size = 10.0
            except Exception:
                pass

        # Grade risk multiplier
        grade_multipliers = {
            TradeQuality.A_PLUS: 1.00,
            TradeQuality.A:      0.75,
            TradeQuality.B:      0.50,
            TradeQuality.C:      0.25,
            TradeQuality.REJECT: 0.00,
        }
        g_mult = grade_multipliers.get(grade, 0.0)

        # Drawdown risk adaptation multiplier
        dd_mult = self.get_drawdown_multiplier(drawdown_pct)

        risk_amount = equity * self.risk_per_trade * g_mult * dd_mult
        if risk_amount <= 0:
            return 0.0

        # Lots = risk_amount / (stop_distance * contract_size)
        lots = risk_amount / (stop_distance * contract_size)
        lots = min(lots, self.max_lots)
        lots = max(lots, 0.01)
        return round(lots, 2)


# Singleton
scorer = SignalScorer()
