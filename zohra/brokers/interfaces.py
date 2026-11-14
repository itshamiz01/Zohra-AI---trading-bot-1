"""
╔══════════════════════════════════════════════════════════════╗
║      MARKET ABSTRACTION LAYER — INTERFACE CONTRACTS         ║
║  Abstract base classes defining the universal broker API     ║
╚══════════════════════════════════════════════════════════════╝

Every broker adapter MUST implement UnifiedBrokerAdapter.
The Trading Core programs against these interfaces, never concrete classes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from zohra.brokers.models import (
    StandardBalance,
    StandardExecution,
    StandardInstrument,
    StandardMargin,
    StandardOrder,
    StandardPosition,
    StandardPortfolio,
    StandardTick,
    StandardTrade,
)


# ════════════════════════════════════════════════════════════════
#  Connection Interface
# ════════════════════════════════════════════════════════════════

class ConnectionInterface(ABC):
    """Lifecycle management for broker connections."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique broker identifier (e.g., 'mt5', 'dhan', 'coindcx')."""
        ...

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the broker. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly disconnect from the broker."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the broker connection is active."""
        ...

    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the broker connection.
        Returns a dict with 'status' ('healthy'/'unhealthy'), 'latency_ms', 'details'.
        Default implementation checks is_connected().
        """
        connected = self.is_connected()
        return {
            "broker": self.name,
            "status": "healthy" if connected else "unhealthy",
            "connected": connected,
            "latency_ms": 0.0,
            "details": {},
        }

    def heartbeat(self) -> bool:
        """
        Lightweight connectivity ping.
        Returns True if the connection is alive.
        Default implementation delegates to is_connected().
        """
        return self.is_connected()

    def reconnect(self) -> bool:
        """
        Attempt to re-establish a dropped connection.
        Default implementation disconnects then connects.
        """
        try:
            self.disconnect()
        except Exception:
            pass
        return self.connect()


# ════════════════════════════════════════════════════════════════
#  Order Interface
# ════════════════════════════════════════════════════════════════

class OrderInterface(ABC):
    """Place, modify, cancel, and query orders."""

    @abstractmethod
    def place_order(self, order: StandardOrder) -> StandardExecution:
        """Submit a new order to the broker. Returns execution result."""
        ...

    @abstractmethod
    def modify_order(self, order_id: str, **kwargs) -> bool:
        """Modify an existing pending order. Returns True on success."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True on success."""
        ...

    def get_orders(self, status: str = None) -> List[StandardOrder]:
        """Get pending/active orders, optionally filtered by status."""
        return []

    def get_order_history(self, days: int = 7) -> List[StandardOrder]:
        """Get historical orders for the last N days."""
        return []


# ════════════════════════════════════════════════════════════════
#  Position Interface
# ════════════════════════════════════════════════════════════════

class PositionInterface(ABC):
    """Query and manage open positions."""

    @abstractmethod
    def get_positions(self, symbol: str = None, magic: int = None) -> List[Dict]:
        """
        Get open positions, optionally filtered.
        Returns list of position dicts (backward-compatible with existing code).
        """
        ...

    @abstractmethod
    def close_position(self, ticket: int, symbol: str,
                       volume: float, direction: str) -> Dict:
        """Close an open position. Returns result dict."""
        ...

    def close_all_positions(self, magic: int = None,
                            comment: str = "Emergency-Close") -> int:
        """Close all open positions. Returns count closed. Default loops get_positions."""
        positions = self.get_positions()
        closed = 0
        for pos in positions:
            if magic and pos.get("magic") != magic:
                continue
            result = self.close_position(
                pos["ticket"], pos["symbol"],
                pos.get("lots", pos.get("volume", 0)),
                pos.get("direction", "LONG")
            )
            if result and result.get("success"):
                closed += 1
        return closed


# ════════════════════════════════════════════════════════════════
#  Market Data Interface
# ════════════════════════════════════════════════════════════════

class MarketDataInterface(ABC):
    """Real-time market data retrieval."""

    @abstractmethod
    def get_tick(self, symbol: str) -> Optional[Dict]:
        """Get current bid/ask tick for a symbol. Returns dict or None."""
        ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> Dict[str, float]:
        """Get current price with bid/ask/mid/spread. Returns dict."""
        ...

    def get_spread_pips(self, symbol: str) -> float:
        """Get current spread in pips. Default implementation uses get_tick."""
        tick = self.get_tick(symbol)
        if not tick:
            return 999.0
        spread = tick.get("ask", 0) - tick.get("bid", 0)
        if "JPY" in symbol:
            return spread * 100
        elif "XAU" in symbol:
            return spread * 10
        else:
            return spread * 10_000


# ════════════════════════════════════════════════════════════════
#  Account Interface
# ════════════════════════════════════════════════════════════════

class AccountInterface(ABC):
    """Account balance and margin information."""

    @abstractmethod
    def get_account_info(self) -> Optional[Dict]:
        """Get full account info dict. Returns None if unavailable."""
        ...

    @abstractmethod
    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary with balance, equity, margin, etc."""
        ...

    def get_equity(self) -> float:
        """Get current account equity. Default uses get_account_info."""
        info = self.get_account_info()
        return info.get("equity", 0.0) if info else 0.0

    def get_balance(self) -> float:
        """Get current account balance. Default uses get_account_info."""
        info = self.get_account_info()
        return info.get("balance", 0.0) if info else 0.0

    def get_margin_info(self) -> StandardMargin:
        """Get margin information. Default uses get_account_info."""
        info = self.get_account_info()
        if not info:
            return StandardMargin()
        return StandardMargin(
            used=info.get("margin", 0.0),
            free=info.get("free_margin", 0.0),
        )


# ════════════════════════════════════════════════════════════════
#  Symbol / Instrument Interface
# ════════════════════════════════════════════════════════════════

class SymbolInterface(ABC):
    """Symbol/instrument metadata and availability."""

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get metadata for a specific symbol. Returns dict or None."""
        ...

    def get_symbols(self) -> List[str]:
        """Get all available symbols. Default returns empty list."""
        return []

    def is_symbol_available(self, symbol: str) -> bool:
        """Check if a symbol is available for trading. Default uses get_symbol_info."""
        return self.get_symbol_info(symbol) is not None


# ════════════════════════════════════════════════════════════════
#  Historical Data Interface
# ════════════════════════════════════════════════════════════════

class HistoricalDataInterface(ABC):
    """Historical OHLCV data retrieval."""

    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str,
                  count: int = 300) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV bars.
        Returns DataFrame with columns: open, high, low, close, tick_volume
        indexed by datetime. Returns None on failure.
        """
        ...

    def get_candles(self, symbol: str, timeframe: str = "H1",
                    count: int = 200) -> pd.DataFrame:
        """Get candles as a flat DataFrame (reset index, volume alias). Default wraps get_ohlcv."""
        df = self.get_ohlcv(symbol, timeframe, count)
        if df is None:
            return pd.DataFrame()
        df_reset = df.reset_index()
        if "tick_volume" in df_reset.columns:
            df_reset.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df_reset

    def get_multi_tf(self, symbol: str, timeframes: List[str],
                     count: int = 300) -> Dict[str, Optional[pd.DataFrame]]:
        """Fetch multiple timeframes at once. Default loops get_ohlcv."""
        return {tf: self.get_ohlcv(symbol, tf, count) for tf in timeframes}


# ════════════════════════════════════════════════════════════════
#  Streaming Interface
# ════════════════════════════════════════════════════════════════

class StreamingInterface(ABC):
    """Real-time data streaming (ticks, candles)."""

    def subscribe_ticks(self, symbol: str,
                        callback: Callable[[StandardTick], None]) -> bool:
        """
        Subscribe to real-time tick updates for a symbol.
        callback receives StandardTick objects.
        Returns True if subscription was successful.
        Default: not supported, returns False.
        """
        return False

    def unsubscribe_ticks(self, symbol: str) -> bool:
        """Unsubscribe from tick updates. Default: returns False."""
        return False

    def subscribe_candles(self, symbol: str, timeframe: str,
                          callback: Callable) -> bool:
        """Subscribe to real-time candle updates. Default: not supported."""
        return False

    def unsubscribe_candles(self, symbol: str, timeframe: str) -> bool:
        """Unsubscribe from candle updates. Default: returns False."""
        return False


# ════════════════════════════════════════════════════════════════
#  Risk Validation Interface
# ════════════════════════════════════════════════════════════════

class RiskValidationInterface(ABC):
    """Pre-trade risk checks at the broker level."""

    def validate_order(self, order: StandardOrder) -> Dict[str, Any]:
        """
        Pre-flight validation of an order before submission.
        Returns dict with 'valid' (bool) and 'reason' (str).
        Default: always valid.
        """
        return {"valid": True, "reason": ""}

    def check_margin(self, symbol: str, volume: float,
                     order_type: str = "MARKET") -> Dict[str, Any]:
        """
        Check if sufficient margin is available for a trade.
        Returns dict with 'sufficient' (bool), 'required', 'available'.
        Default: always sufficient.
        """
        return {"sufficient": True, "required": 0.0, "available": 0.0}

    def check_limits(self, symbol: str) -> Dict[str, Any]:
        """
        Check broker-side trading limits for a symbol.
        Returns dict with limit details.
        Default: no limits.
        """
        return {"within_limits": True, "details": {}}


# ════════════════════════════════════════════════════════════════
#  Execution Interface
# ════════════════════════════════════════════════════════════════

class ExecutionInterface(ABC):
    """Direct execution methods (convenience layer over OrderInterface)."""

    def execute_market_order(self, symbol: str, side: str,
                             volume: float, sl: float = 0.0,
                             tp: float = 0.0, **kwargs) -> StandardExecution:
        """
        Execute a market order immediately.
        Default: constructs a StandardOrder and delegates to place_order.
        """
        from zohra.brokers.models import OrderSide, OrderType
        order = StandardOrder(
            symbol=symbol,
            side=OrderSide.BUY if side.upper() in ("BUY", "LONG") else OrderSide.SELL,
            order_type=OrderType.MARKET,
            volume=volume,
            stop_loss=sl,
            take_profit=tp,
            magic=kwargs.get("magic", 0),
            comment=kwargs.get("comment", ""),
        )
        return self.place_order(order)

    def execute_limit_order(self, symbol: str, side: str,
                            volume: float, price: float,
                            sl: float = 0.0, tp: float = 0.0,
                            **kwargs) -> StandardExecution:
        """Execute a limit order. Default constructs order and delegates."""
        from zohra.brokers.models import OrderSide, OrderType
        order = StandardOrder(
            symbol=symbol,
            side=OrderSide.BUY if side.upper() in ("BUY", "LONG") else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            volume=volume,
            price=price,
            stop_loss=sl,
            take_profit=tp,
            magic=kwargs.get("magic", 0),
            comment=kwargs.get("comment", ""),
        )
        return self.place_order(order)

    def execute_stop_order(self, symbol: str, side: str,
                           volume: float, price: float,
                           sl: float = 0.0, tp: float = 0.0,
                           **kwargs) -> StandardExecution:
        """Execute a stop order. Default constructs order and delegates."""
        from zohra.brokers.models import OrderSide, OrderType
        order = StandardOrder(
            symbol=symbol,
            side=OrderSide.BUY if side.upper() in ("BUY", "LONG") else OrderSide.SELL,
            order_type=OrderType.STOP,
            volume=volume,
            price=price,
            stop_loss=sl,
            take_profit=tp,
            magic=kwargs.get("magic", 0),
            comment=kwargs.get("comment", ""),
        )
        return self.place_order(order)


# ════════════════════════════════════════════════════════════════
#  Portfolio Interface
# ════════════════════════════════════════════════════════════════

class PortfolioInterface(ABC):
    """Portfolio-level aggregation and exposure analysis."""

    def get_portfolio_summary(self) -> StandardPortfolio:
        """Get portfolio summary including all positions and balance. Default builds from parts."""
        positions = self.get_positions() if hasattr(self, "get_positions") else []
        total_pnl = sum(p.get("profit", p.get("pnl", 0)) for p in positions)
        total_volume = sum(p.get("lots", p.get("volume", 0)) for p in positions)

        return StandardPortfolio(
            total_positions=len(positions),
            total_pnl=total_pnl,
            total_volume=total_volume,
            broker=self.name if hasattr(self, "name") else "",
        )

    def get_exposure(self) -> Dict[str, float]:
        """Get exposure by symbol. Default aggregates from positions."""
        positions = self.get_positions() if hasattr(self, "get_positions") else []
        exposure = {}
        for pos in positions:
            sym = pos.get("symbol", "")
            vol = pos.get("lots", pos.get("volume", 0))
            direction_mult = 1.0 if pos.get("direction") == "LONG" else -1.0
            exposure[sym] = exposure.get(sym, 0.0) + (vol * direction_mult)
        return exposure

    def get_pnl_summary(self) -> Dict[str, float]:
        """Get P&L summary by symbol. Default aggregates from positions."""
        positions = self.get_positions() if hasattr(self, "get_positions") else []
        pnl_map = {}
        for pos in positions:
            sym = pos.get("symbol", "")
            pnl = pos.get("profit", pos.get("pnl", 0))
            pnl_map[sym] = pnl_map.get(sym, 0.0) + pnl
        return pnl_map


# ════════════════════════════════════════════════════════════════
#  Unified Broker Adapter (Master Interface)
# ════════════════════════════════════════════════════════════════

class UnifiedBrokerAdapter(
    ConnectionInterface,
    OrderInterface,
    PositionInterface,
    MarketDataInterface,
    AccountInterface,
    SymbolInterface,
    HistoricalDataInterface,
    StreamingInterface,
    RiskValidationInterface,
    ExecutionInterface,
    PortfolioInterface,
):
    """
    Complete broker adapter contract.

    Every broker adapter (MT5, Dhan, CoinDCX, etc.) MUST extend this class
    and implement all abstract methods. Non-abstract methods provide sensible
    defaults that can be overridden.

    Usage:
        class MyBrokerAdapter(UnifiedBrokerAdapter):
            @property
            def name(self) -> str:
                return "mybroker"

            def connect(self) -> bool:
                ...
            # ... implement all abstract methods
    """
    pass
