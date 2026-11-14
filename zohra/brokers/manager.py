"""
╔══════════════════════════════════════════════════════════════╗
║        MARKET ABSTRACTION LAYER — BROKER MANAGER            ║
║  Central facade routing all broker operations               ║
╚══════════════════════════════════════════════════════════════╝

BrokerManager is the SINGLE entry point for all Trading Core
broker interactions. It replaces direct mt5_broker imports.

Usage:
    from zohra.brokers.manager import broker_manager

    broker_manager.connect()
    equity = broker_manager.get_equity()
    broker_manager.open_trade("EURUSD", "LONG", 0.1, sl, tp)
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from zohra.brokers.interfaces import UnifiedBrokerAdapter
from zohra.brokers.resilience import reconnection_manager

logger = logging.getLogger("zohra.broker_manager")


class BrokerManager:
    """
    Central facade for all broker operations.

    - Maintains a registry of broker adapters (MT5, Dhan, CoinDCX, etc.)
    - Routes calls to the default or specified broker adapter
    - Supports simultaneous multi-broker operation
    - Provides backward-compatible API surface matching mt5_broker
    """

    def __init__(self):
        self._adapters: Dict[str, Any] = {}
        self._default: Optional[str] = None
        self._lock = threading.Lock()

    # ════════════════════════════════════════════════
    #  Registry
    # ════════════════════════════════════════════════

    def register_adapter(self, name: str, adapter: Any) -> None:
        """
        Register a broker adapter.
        The first registered adapter becomes the default.
        """
        with self._lock:
            self._adapters[name] = adapter
            if self._default is None:
                self._default = name
            # Register with reconnection manager
            reconnection_manager.register(name, adapter)
            logger.info(f"Registered broker adapter: {name}")

    def unregister_adapter(self, name: str) -> None:
        """Remove a broker adapter from the registry."""
        with self._lock:
            self._adapters.pop(name, None)
            reconnection_manager.unregister(name)
            if self._default == name:
                self._default = next(iter(self._adapters), None)

    def get_adapter(self, name: str = None) -> Any:
        """
        Get a specific broker adapter by name.
        If name is None, returns the default adapter.
        Raises KeyError if adapter not found.
        """
        target = name or self._default
        if target is None:
            raise KeyError("No broker adapters registered")
        adapter = self._adapters.get(target)
        if adapter is None:
            raise KeyError(f"Broker adapter '{target}' not registered. "
                           f"Available: {list(self._adapters.keys())}")
        return adapter

    def get_default_adapter(self) -> Any:
        """Get the default broker adapter."""
        return self.get_adapter(None)

    def set_default(self, name: str) -> None:
        """Set the default broker."""
        if name not in self._adapters:
            raise KeyError(f"Broker '{name}' not registered")
        self._default = name
        logger.info(f"Default broker set to: {name}")

    def get_registered_brokers(self) -> List[str]:
        """Get list of registered broker names."""
        return list(self._adapters.keys())

    @property
    def default_broker(self) -> Optional[str]:
        """Name of the current default broker."""
        return self._default

    def _resolve(self, broker: str = None) -> Any:
        """Resolve broker name to adapter instance."""
        return self.get_adapter(broker)

    # ════════════════════════════════════════════════
    #  Connection Interface
    # ════════════════════════════════════════════════

    def connect(self, broker: str = None) -> bool:
        """Connect to the specified or default broker."""
        return self._resolve(broker).connect()

    def disconnect(self, broker: str = None) -> None:
        """Disconnect from the specified or default broker."""
        self._resolve(broker).disconnect()

    def is_connected(self, broker: str = None) -> bool:
        """Check if the specified or default broker is connected."""
        try:
            return self._resolve(broker).is_connected()
        except KeyError:
            return False

    def health_check(self, broker: str = None) -> Dict[str, Any]:
        """Health check for the specified or default broker."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "health_check"):
            return adapter.health_check()
        return {
            "broker": getattr(adapter, "name", broker),
            "status": "healthy" if adapter.is_connected() else "unhealthy",
            "connected": adapter.is_connected(),
        }

    def heartbeat(self, broker: str = None) -> bool:
        """Heartbeat ping for the specified or default broker."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "heartbeat"):
            return adapter.heartbeat()
        return adapter.is_connected()

    def reconnect(self, broker: str = None) -> bool:
        """Reconnect the specified or default broker."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "reconnect"):
            return adapter.reconnect()
        try:
            adapter.disconnect()
        except Exception:
            pass
        return adapter.connect()

    # Multi-broker connection
    def connect_all(self) -> Dict[str, bool]:
        """Connect all registered brokers. Returns {name: success}."""
        results = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = adapter.connect()
            except Exception as e:
                logger.error(f"Failed to connect {name}: {e}")
                results[name] = False
        return results

    def disconnect_all(self) -> None:
        """Disconnect all registered brokers."""
        for name, adapter in self._adapters.items():
            try:
                adapter.disconnect()
            except Exception as e:
                logger.error(f"Failed to disconnect {name}: {e}")

    def health_check_all(self) -> Dict[str, Dict]:
        """Health check all registered brokers."""
        results = {}
        for name in self._adapters:
            try:
                results[name] = self.health_check(name)
            except Exception as e:
                results[name] = {"broker": name, "status": "error", "error": str(e)}
        return results

    # ════════════════════════════════════════════════
    #  Account Interface
    # ════════════════════════════════════════════════

    def get_account_info(self, broker: str = None) -> Optional[Dict]:
        """Get full account info from the specified or default broker."""
        return self._resolve(broker).get_account_info()

    def get_account_summary(self, broker: str = None) -> Dict[str, Any]:
        """Get account summary from the specified or default broker."""
        return self._resolve(broker).get_account_summary()

    def get_balances(self, broker: str = None) -> Dict[str, float]:
        """Return broker wallet balances when the adapter exposes them."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "get_balances"):
            return adapter.get_balances()
        return {}

    def get_equity(self, broker: str = None) -> float:
        """Get current equity from the specified or default broker."""
        return self._resolve(broker).get_equity()

    def get_balance(self, broker: str = None) -> float:
        """Get current balance from the specified or default broker."""
        return self._resolve(broker).get_balance()

    # ════════════════════════════════════════════════
    #  Market Data Interface
    # ════════════════════════════════════════════════

    def get_tick(self, symbol: str, broker: str = None) -> Optional[Dict]:
        """Get current tick data for a symbol."""
        return self._resolve(broker).get_tick(symbol)

    def get_current_price(self, symbol: str, broker: str = None) -> Dict[str, float]:
        """Get current price with bid/ask/mid/spread."""
        return self._resolve(broker).get_current_price(symbol)

    def get_spread_pips(self, symbol: str, broker: str = None) -> float:
        """Get current spread in pips."""
        return self._resolve(broker).get_spread_pips(symbol)

    # ════════════════════════════════════════════════
    #  Historical Data Interface
    # ════════════════════════════════════════════════

    def get_ohlcv(self, symbol: str, timeframe: str,
                  count: int = 300, broker: str = None) -> Optional[pd.DataFrame]:
        """Fetch OHLCV bars from the specified or default broker."""
        return self._resolve(broker).get_ohlcv(symbol, timeframe, count)

    def get_candles(self, symbol: str, timeframe: str = "H1",
                    count: int = 200, broker: str = None) -> pd.DataFrame:
        """Get candles as a flat DataFrame."""
        return self._resolve(broker).get_candles(symbol, timeframe, count)

    def get_multi_tf(self, symbol: str, timeframes: List[str],
                     count: int = 300, broker: str = None) -> Dict[str, Optional[pd.DataFrame]]:
        """Fetch multiple timeframes at once."""
        return self._resolve(broker).get_multi_tf(symbol, timeframes, count)

    # ════════════════════════════════════════════════
    #  Order / Trade Execution Interface
    # ════════════════════════════════════════════════

    def open_trade(self, symbol: str, direction: str, lots: float,
                   stop_loss: float, take_profit: float,
                   magic: int = None, comment: str = "Zohra",
                   broker: str = None) -> Optional[Dict]:
        """
        Open a market order. Backward-compatible with MT5Broker.open_trade().
        Returns trade dict with ticket, or None on failure.
        """
        return self._resolve(broker).open_trade(
            symbol, direction, lots, stop_loss, take_profit,
            magic=magic, comment=comment
        )

    def open_position(self, order: Dict, broker: str = None) -> Dict:
        """Open a position from an order dict. Backward-compatible."""
        return self._resolve(broker).open_position(order)

    def close_trade(self, ticket: int, symbol: str, direction: str,
                    lots: float = None, comment: str = "Zohra-Close",
                    broker: str = None) -> Optional[Dict]:
        """Close a position by ticket. Backward-compatible."""
        return self._resolve(broker).close_trade(
            ticket, symbol, direction, lots=lots, comment=comment
        )

    def close_position(self, ticket: int, symbol: str,
                       volume: float, direction: str,
                       broker: str = None) -> Dict:
        """Close position. Backward-compatible interface."""
        return self._resolve(broker).close_position(ticket, symbol, volume, direction)

    def modify_trade(self, ticket: int, new_sl: float = None,
                     new_tp: float = None, broker: str = None) -> bool:
        """Modify SL/TP on open position. Backward-compatible."""
        return self._resolve(broker).modify_trade(ticket, new_sl=new_sl, new_tp=new_tp)

    def modify_stop(self, ticket: int, symbol: str,
                    stop_loss: float, take_profit: Optional[float] = None,
                    broker: str = None) -> Dict:
        """Modify stops. Backward-compatible."""
        return self._resolve(broker).modify_stop(ticket, symbol, stop_loss, take_profit)

    def close_all_positions(self, magic: int = None,
                            comment: str = "Emergency-Close",
                            broker: str = None) -> int:
        """Close all open positions."""
        return self._resolve(broker).close_all_positions(magic=magic, comment=comment)

    # ════════════════════════════════════════════════
    #  Position Query Interface
    # ════════════════════════════════════════════════

    def get_open_positions(self, magic: int = None,
                           symbol: str = None,
                           broker: str = None) -> List[Dict]:
        """Get open positions from the specified or default broker."""
        adapter = self._resolve(broker)
        # Support both signatures (with and without kwargs)
        try:
            return adapter.get_open_positions(magic=magic, symbol=symbol)
        except TypeError:
            # Fallback for adapters that only accept positional args
            positions = adapter.get_open_positions()
            if magic:
                positions = [p for p in positions if p.get("magic") == magic]
            if symbol:
                positions = [p for p in positions if p.get("symbol") == symbol]
            return positions

    # Alias for PositionInterface
    def get_positions(self, symbol: str = None,
                      magic: int = None,
                      broker: str = None) -> List[Dict]:
        """Alias for get_open_positions (interface compliance)."""
        return self.get_open_positions(magic=magic, symbol=symbol, broker=broker)

    # ════════════════════════════════════════════════
    #  Symbol Interface
    # ════════════════════════════════════════════════

    def get_symbol_info(self, symbol: str, broker: str = None) -> Optional[Dict]:
        """Get symbol metadata."""
        return self._resolve(broker).get_symbol_info(symbol)

    def get_symbols(self, broker: str = None) -> List[str]:
        """Get all available symbols."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "get_symbols"):
            return adapter.get_symbols()
        return []

    # ════════════════════════════════════════════════
    #  Streaming Interface
    # ════════════════════════════════════════════════

    def subscribe_ticks(self, symbol: str,
                        callback: Callable, broker: str = None) -> bool:
        """Subscribe to real-time tick updates."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "subscribe_ticks"):
            return adapter.subscribe_ticks(symbol, callback)
        return False

    def unsubscribe_ticks(self, symbol: str, broker: str = None) -> bool:
        """Unsubscribe from tick updates."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "unsubscribe_ticks"):
            return adapter.unsubscribe_ticks(symbol)
        return False

    # ════════════════════════════════════════════════
    #  MT5-Specific Pass-Through (Backward Compat)
    # ════════════════════════════════════════════════

    def is_autotrading_enabled(self, broker: str = None) -> bool:
        """Check if autotrading is enabled (MT5-specific but safe for all)."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "is_autotrading_enabled"):
            return adapter.is_autotrading_enabled()
        return True  # Non-MT5 brokers don't have this concept

    def _check_autotrading_status(self, broker: str = None):
        """MT5 autotrading status check. Safe to call on any adapter."""
        adapter = self._resolve(broker)
        if hasattr(adapter, "_check_autotrading_status"):
            return adapter._check_autotrading_status()
        return True

    # ════════════════════════════════════════════════
    #  Dynamic attribute delegation
    # ════════════════════════════════════════════════

    def __getattr__(self, name: str) -> Any:
        """
        Fall back to the default adapter for any method not explicitly
        defined on BrokerManager. This ensures 100% backward compatibility
        with any mt5_broker method that consumer code might call.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            adapter = self.get_default_adapter()
            attr = getattr(adapter, name)
            return attr
        except (KeyError, AttributeError):
            raise AttributeError(
                f"'{type(self).__name__}' has no attribute '{name}' "
                f"and no default adapter provides it"
            )


# ════════════════════════════════════════════════════════════════
#  Global Singleton
# ════════════════════════════════════════════════════════════════

broker_manager = BrokerManager()
