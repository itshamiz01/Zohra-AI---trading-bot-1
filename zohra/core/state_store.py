# zohra/core/state_store.py
import threading
from typing import Dict, Any, Callable, List
from zohra.config.settings import STATE, TradingState
from zohra.event_bus import event_bus

class StateStore:
    """
    Thread-safe reactive state manager wrapping the global TradingState.
    Publishes events to the EventBus on state transitions to keep clients updated.
    """
    def __init__(self, raw_state: TradingState = STATE):
        self._state = raw_state
        self._lock = threading.RLock()
        self._listeners: Dict[str, List[Callable[[Any], None]]] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Thread-safe access to a state attribute."""
        with self._lock:
            return getattr(self._state, key, default)

    def set(self, key: str, value: Any):
        """Thread-safe modification of state. Publishes state_changed event."""
        old_val = None
        changed = False
        with self._lock:
            if hasattr(self._state, key):
                old_val = getattr(self._state, key)
                if old_val != value:
                    setattr(self._state, key, value)
                    changed = True
            else:
                setattr(self._state, key, value)
                changed = True

        if changed:
            event_data = {
                "key": key,
                "old_value": old_val,
                "new_value": value
            }
            # Trigger registered callbacks
            if key in self._listeners:
                for callback in self._listeners[key]:
                    try:
                        callback(value)
                    except Exception:
                        pass
            
            # Publish to the global EventBus asynchronously
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(event_bus.publish("state_changed", event_data))
                else:
                    loop.run_until_complete(event_bus.publish("state_changed", event_data))
            except Exception:
                # Fallback to threaded background publish if event loop is not active
                t = threading.Thread(
                    target=lambda: asyncio.run(event_bus.publish("state_changed", event_data)),
                    daemon=True
                )
                t.start()

    def subscribe(self, key: str, callback: Callable[[Any], None]):
        """Register a callback for changes on a specific state key."""
        with self._lock:
            if key not in self._listeners:
                self._listeners[key] = []
            self._listeners[key].append(callback)

    def get_all(self) -> Dict[str, Any]:
        """Returns snapshot of current state fields."""
        with self._lock:
            return {
                "daily_pnl": getattr(self._state, "daily_pnl", 0.0),
                "weekly_pnl": getattr(self._state, "weekly_pnl", 0.0),
                "monthly_pnl": getattr(self._state, "monthly_pnl", 0.0),
                "daily_trades": getattr(self._state, "daily_trades", 0),
                "trading_enabled": getattr(self._state, "trading_enabled", True),
                "trading_halted": getattr(self._state, "trading_halted", False),
                "halt_reason": getattr(self._state, "halt_reason", ""),
                "last_trade_time": getattr(self._state, "last_trade_time", ""),
                "session_equity": getattr(self._state, "session_equity", 0.0),
                "peak_equity": getattr(self._state, "peak_equity", 0.0),
            }

# Central singleton instance
state_store = StateStore()
