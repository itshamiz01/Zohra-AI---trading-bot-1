"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — STRATEGY DEVELOPMENT KIT (SDK)                    ║
║   Build New Strategies Without Modifying Trading Core               ║
╚══════════════════════════════════════════════════════════════════════╝

Every strategy should be installable with minimal configuration.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger("zohra.intelligence.sdk")


# ════════════════════════════════════════════════════════════════
#  STRATEGY TEMPLATE
# ════════════════════════════════════════════════════════════════

class StrategyTemplate(ABC):
    """
    Base class for SDK-developed strategies.
    Implement the lifecycle hooks to create a new strategy.
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.sdk: Optional['StrategySDK'] = None

    def bind_sdk(self, sdk: 'StrategySDK'):
        """Bind the SDK context to this strategy."""
        self.sdk = sdk

    @abstractmethod
    def on_init(self):
        """Called when the strategy is initialized."""
        ...

    @abstractmethod
    def on_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """
        Called on each scan cycle.
        Return a signal dict or None:
        {
            "direction": "LONG" | "SHORT",
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float,
            "confidence": float,
            "reason": str,
        }
        """
        ...

    def on_fill(self, order_result: Dict):
        """Called when an order is filled."""
        pass

    def on_close(self, trade_result: Dict):
        """Called when a position is closed."""
        pass


# ════════════════════════════════════════════════════════════════
#  INDICATOR LIBRARY
# ════════════════════════════════════════════════════════════════

class IndicatorLibrary:
    """Pre-built technical indicators for SDK strategies."""

    @staticmethod
    def ema(close: np.ndarray, period: int) -> np.ndarray:
        alpha = 2.0 / (period + 1)
        result = np.zeros_like(close, dtype=float)
        result[0] = close[0]
        for i in range(1, len(close)):
            result[i] = alpha * close[i] + (1 - alpha) * result[i - 1]
        return result

    @staticmethod
    def sma(close: np.ndarray, period: int) -> np.ndarray:
        result = np.full_like(close, np.nan, dtype=float)
        for i in range(period - 1, len(close)):
            result[i] = np.mean(close[i - period + 1:i + 1])
        return result

    @staticmethod
    def rsi(close: np.ndarray, period: int = 14) -> float:
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        return 100 - (100 / (1 + avg_gain / avg_loss))

    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        if len(high) < period + 1:
            return 0.0
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        return float(np.mean(tr[-period:]))

    @staticmethod
    def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        if len(high) < period + 1:
            return 0.0
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        atr_val = np.mean(tr[-period:])
        if atr_val < 1e-9:
            return 0.0
        plus_dm = np.where((np.diff(high) > -np.diff(low)) & (np.diff(high) > 0), np.diff(high), 0)
        minus_dm = np.where((-np.diff(low) > np.diff(high)) & (-np.diff(low) > 0), -np.diff(low), 0)
        plus_di = 100 * np.mean(plus_dm[-period:]) / atr_val
        minus_di = 100 * np.mean(minus_dm[-period:]) / atr_val
        if plus_di + minus_di == 0:
            return 0.0
        return 100 * abs(plus_di - minus_di) / (plus_di + minus_di)

    @staticmethod
    def bollinger_bands(close: np.ndarray, period: int = 20, num_std: float = 2.0):
        sma = np.mean(close[-period:])
        std = np.std(close[-period:])
        return {"upper": sma + num_std * std, "middle": sma, "lower": sma - num_std * std, "width": (2 * num_std * std) / max(sma, 1e-9) * 100}

    @staticmethod
    def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
        fast_ema = IndicatorLibrary.ema(close, fast)
        slow_ema = IndicatorLibrary.ema(close, slow)
        macd_line = fast_ema - slow_ema
        signal_line = IndicatorLibrary.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return {"macd": float(macd_line[-1]), "signal": float(signal_line[-1]), "histogram": float(histogram[-1])}


# ════════════════════════════════════════════════════════════════
#  STRATEGY SDK
# ════════════════════════════════════════════════════════════════

class StrategySDK:
    """
    Complete development kit for building new strategies.
    Exposes market data, portfolio, risk, indicators, SMC, macro,
    orders, logging, and event APIs.
    """

    def __init__(self):
        self.indicators = IndicatorLibrary()
        self._strategies: Dict[str, StrategyTemplate] = {}

    # ─── Market Data API ──────────────────────────────────────

    @staticmethod
    def market_data(symbol: str, timeframe: str, count: int = 100, broker: str = "mt5") -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for a symbol."""
        try:
            from zohra.brokers.manager import broker_manager
            return broker_manager.get_ohlcv(symbol, timeframe, count=count, broker=broker)
        except Exception as e:
            logger.warning(f"SDK market_data error: {e}")
            return None

    # ─── Portfolio API ────────────────────────────────────────

    @staticmethod
    def portfolio() -> Dict[str, Any]:
        """Get current portfolio snapshot."""
        try:
            from zohra.intelligence.portfolio_intelligence import portfolio_intel
            return portfolio_intel.get_snapshot()
        except Exception:
            return {"error": "Portfolio intelligence not available"}

    # ─── Risk API ─────────────────────────────────────────────

    @staticmethod
    def risk_check(symbol: str, direction: str, lot_size: float) -> Dict[str, Any]:
        """Validate a trade against risk rules."""
        try:
            from zohra.core.risk_guardian import risk_guardian
            return risk_guardian.validate_signal({
                "symbol": symbol, "direction": direction,
                "volume": lot_size, "type": "sdk_check",
            })
        except Exception:
            return {"approved": True, "reason": "Risk guardian not available — defaulting to approved"}

    # ─── Smart Money API ──────────────────────────────────────

    @staticmethod
    def smart_money(symbol: str, timeframe: str = "M15", broker: str = "mt5") -> Dict[str, Any]:
        """Get Smart Money analysis for a symbol."""
        try:
            from zohra.intelligence.smart_money import smc_engine
            from zohra.brokers.manager import broker_manager
            df = broker_manager.get_ohlcv(symbol, timeframe, count=100, broker=broker)
            if df is not None:
                return smc_engine.analyze(df, symbol, timeframe).to_dict()
        except Exception:
            pass
        return {"confidence": 0, "bias": "NEUTRAL"}

    # ─── Macro API ────────────────────────────────────────────

    @staticmethod
    def macro_events(hours_ahead: int = 4) -> List[Dict]:
        """Get upcoming macro events."""
        try:
            from zohra.intelligence.macro_intelligence import macro_engine
            events = macro_engine.get_upcoming_events(hours_ahead)
            return [e.to_dict() for e in events]
        except Exception:
            return []

    # ─── Order API ────────────────────────────────────────────

    @staticmethod
    def place_order(symbol: str, direction: str, lot_size: float,
                    stop_loss: float, take_profit: float, broker: str = "mt5") -> Dict[str, Any]:
        """Place an order through the broker manager."""
        try:
            from zohra.brokers.manager import broker_manager
            return broker_manager.place_order(
                symbol=symbol, direction=direction, volume=lot_size,
                sl=stop_loss, tp=take_profit, broker=broker,
            )
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def close_position(ticket: int, broker: str = "mt5") -> Dict[str, Any]:
        """Close a position by ticket."""
        try:
            from zohra.brokers.manager import broker_manager
            return broker_manager.close_position(ticket, broker=broker)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Logging API ──────────────────────────────────────────

    @staticmethod
    def log(message: str, level: str = "info"):
        """Log a message from a strategy."""
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(f"[SDK] {message}")

    # ─── Event API ────────────────────────────────────────────

    @staticmethod
    async def emit_event(event_type: str, data: Any):
        """Publish an event to the EventBus."""
        try:
            from zohra.event_bus import event_bus
            await event_bus.publish(event_type, data)
        except Exception as e:
            logger.warning(f"SDK emit_event error: {e}")

    # ─── Strategy Management ──────────────────────────────────

    def install_strategy(self, strategy: StrategyTemplate) -> bool:
        """Install and initialize a strategy."""
        strategy.bind_sdk(self)
        strategy.on_init()
        self._strategies[strategy.name] = strategy
        logger.info(f"📦 Strategy installed: {strategy.name} v{strategy.version}")
        return True

    def run_strategy(self, name: str, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """Run a strategy's signal generation."""
        strategy = self._strategies.get(name)
        if not strategy:
            return None
        return strategy.on_signal(df, symbol)

    # ─── Validation ───────────────────────────────────────────

    @staticmethod
    def validate_signal(signal: Optional[Dict]) -> Dict[str, Any]:
        """Validate a strategy signal format."""
        if signal is None:
            return {"valid": True, "reason": "No signal (WAIT)"}

        required = ["direction", "entry_price", "stop_loss", "take_profit"]
        missing = [k for k in required if k not in signal]
        if missing:
            return {"valid": False, "reason": f"Missing fields: {missing}"}

        if signal["direction"] not in ("LONG", "SHORT"):
            return {"valid": False, "reason": f"Invalid direction: {signal['direction']}"}

        if signal["stop_loss"] <= 0 or signal["take_profit"] <= 0:
            return {"valid": False, "reason": "SL and TP must be positive"}

        return {"valid": True, "reason": "Signal format OK"}

    # ─── Quick Backtest ───────────────────────────────────────

    def backtest(self, strategy_name: str, symbol: str, timeframe: str = "H1",
                 count: int = 500, broker: str = "mt5") -> Dict[str, Any]:
        """Quick backtesting utility for SDK strategies."""
        strategy = self._strategies.get(strategy_name)
        if not strategy:
            return {"error": f"Strategy {strategy_name} not installed"}

        df = self.market_data(symbol, timeframe, count, broker)
        if df is None or len(df) < 100:
            return {"error": "Insufficient data for backtesting"}

        wins = 0
        losses = 0
        total_profit = 0.0

        # Walk-forward simulation
        for i in range(100, len(df) - 1):
            window = df.iloc[:i].copy()
            signal = strategy.on_signal(window, symbol)
            if signal and signal.get("direction") in ("LONG", "SHORT"):
                next_close = float(df.iloc[i + 1]["close"])
                entry = signal.get("entry_price", float(df.iloc[i]["close"]))
                sl = signal.get("stop_loss", 0)
                tp = signal.get("take_profit", 0)

                if signal["direction"] == "LONG":
                    profit = next_close - entry
                else:
                    profit = entry - next_close

                if profit > 0:
                    wins += 1
                else:
                    losses += 1
                total_profit += profit

        total = wins + losses
        return {
            "strategy": strategy_name,
            "symbol": symbol,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(total, 1) * 100, 2),
            "total_profit": round(total_profit, 4),
            "profit_factor": round(wins / max(losses, 1), 2),
        }
