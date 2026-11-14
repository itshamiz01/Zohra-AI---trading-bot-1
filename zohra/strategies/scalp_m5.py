"""
M5 Scalping Engine — extracted from trading_bot2/scalping_module.py
Adapted for MetaTrader 5 (symbols without underscore, lots-based sizing).
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from zohra.core.enums import StrategyName
from zohra.logging.rejection_logger import RejectionLogger

MAX_DAILY_TRADES = 2
RISK_PER_TRADE = 0.005
MIN_RR = 1.5
MAX_SPREAD_PIPS = 2.0
SESSION_START = time(13, 0)
SESSION_END = time(17, 0)
MIN_ADX = 20
STRONG_ADX = 25
STALL_BARS = 3

# MT5 symbol format (no underscores)
SCALP_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]


@dataclass
class ScalpState:
    daily_trade_count: int = 0
    last_trade_date: Optional[datetime] = None
    active_scalps: List[Dict] = field(default_factory=list)


class ScalpM5Engine:
    """Conservative 5M scalping add-on for London/NY overlap."""

    @classmethod
    def metadata(cls):
        """Structured metadata for the Strategy Registry (Phase 2)."""
        return {
            "name": "scalp_m5",
            "category": "Scalping",
            "applicable_regimes": ["trending", "volatile", "breakout"],
            "applicable_sessions": ["Overlap"],
            "applicable_timeframes": ["M5"],
            "min_rrr": 1.5,
            "description": "Conservative 5M scalping add-on for London/NY overlap."
        }

    def __init__(self, broker=None, rejection_logger: Optional[RejectionLogger] = None):
        self.broker = broker
        self.rejection_logger = rejection_logger or RejectionLogger()
        self.state = ScalpState()
        self.timeframe = "M5"
        self.pairs = SCALP_PAIRS

    def _is_session_active(self) -> bool:
        now = datetime.utcnow().time()
        return SESSION_START <= now <= SESSION_END

    def _reset_daily(self):
        today = datetime.utcnow().date()
        if self.state.last_trade_date and self.state.last_trade_date.date() != today:
            self.state.daily_trade_count = 0
        self.state.last_trade_date = datetime.utcnow()

    def can_trade(self, symbol: str, spread_pips: float) -> tuple:
        self._reset_daily()
        failed = []
        if not self._is_session_active():
            failed.append("session")
        if self.state.daily_trade_count >= MAX_DAILY_TRADES:
            failed.append("daily_limit")
        if spread_pips > MAX_SPREAD_PIPS:
            failed.append("spread")
        if failed:
            return False, failed
        return True, []

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return None

        if len(df) < 50:
            return None

        df = df.copy()
        df["ema8"] = df["close"].ewm(span=8).mean()
        df["ema21"] = df["close"].ewm(span=21).mean()
        df["adx"] = self._adx(df, 14)
        df["vol_sma"] = df["volume"].rolling(20).mean()

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        adx = latest["adx"]

        if adx < MIN_ADX:
            self._log_rejection(symbol, 0, ["adx"], f"ADX {adx:.1f} below {MIN_ADX}")
            return None
        if latest["volume"] < latest["vol_sma"]:
            self._log_rejection(symbol, 30, ["volume"], "Volume below SMA")
            return None

        direction = None
        if prev["ema8"] <= prev["ema21"] and latest["ema8"] > latest["ema21"]:
            direction = "LONG"
        elif prev["ema8"] >= prev["ema21"] and latest["ema8"] < latest["ema21"]:
            direction = "SHORT"

        if not direction:
            return None

        atr = self._atr(df, 14).iloc[-1]
        entry = latest["close"]
        if direction == "LONG":
            sl = entry - atr * 1.0
            tp = entry + atr * 1.5
        else:
            sl = entry + atr * 1.0
            tp = entry - atr * 1.5

        rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
        if rr < MIN_RR:
            self._log_rejection(symbol, 50, ["rr"], f"R:R {rr:.2f} below {MIN_RR}")
            return None

        confidence = min(60 + int(adx), 95)
        return {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "confidence_score": confidence,
            "strategy": StrategyName.SCALP_M5.value,
            "adx": adx,
            "strong_momentum": adx >= STRONG_ADX,
        }

    def _log_rejection(self, symbol: str, score: float, failed: List[str], reason: str):
        self.rejection_logger.log_simple(
            symbol=symbol,
            confidence_score=score,
            failed_conditions=failed,
            reason_for_rejection=reason,
            strategy=StrategyName.SCALP_M5,
        )

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
        atr = ScalpM5Engine._atr(df, period)
        plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.rolling(period).mean()
