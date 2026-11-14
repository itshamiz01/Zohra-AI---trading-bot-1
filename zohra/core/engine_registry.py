"""
╔══════════════════════════════════════════════════════════════════════╗
║                  ZOHRA — ENGINE REGISTRY                             ║
║         Centralized Market Engine Lifecycle Controller               ║
║                                                                      ║
║  Manages start/stop/status of all three market engines:             ║
║  - Forex (MT5 pairs via ZohraBrain symbol workers)                   ║
║  - Indian (NSE/BSE via Dhan adapter)                                 ║
║  - Crypto (BTC/ETH via CoinDCX adapter)                              ║
║                                                                      ║
║  Zohra can command: "run only forex engine", "stop crypto engine",  ║
║  "run all engines", "what engines are running?"                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import threading
import time
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger("zohra.engine_registry")

# Thread-safety lock for registry state mutations
_registry_lock = threading.Lock()


class EngineRegistry:
    """
    Singleton registry tracking lifecycle state of all market-specific engines.
    Provides a unified API for starting, stopping, and querying engine status
    from any Zohra interface (chat, voice, CLI, API).
    """

    VALID_ENGINES = {"forex", "indian", "crypto"}

    # Human-friendly display names
    DISPLAY_NAMES = {
        "forex": "Forex Market Engine (MT5)",
        "indian": "Indian Market Engine (Dhan/NSE/BSE)",
        "crypto": "Crypto Market Engine (CoinDCX)",
    }

    def __init__(self):
        self._engines: Dict[str, Dict[str, Any]] = {}
        # Track which engines are *requested* to be active.
        # Actual start/stop is delegated to the engine instance callbacks.
        self._active_set: set = set()

    # ─── Registration ─────────────────────────────────────────

    def register(self, name: str, instance: Any,
                 start_callback=None, stop_callback=None) -> None:
        """
        Register an engine with optional start/stop callbacks.

        Args:
            name: Engine identifier ("forex", "indian", "crypto").
            instance: The engine object (for status queries).
            start_callback: Callable to invoke when starting this engine.
            stop_callback: Callable to invoke when stopping this engine.
        """
        if name not in self.VALID_ENGINES:
            logger.warning(f"Attempted to register unknown engine: {name}")
            return

        with _registry_lock:
            self._engines[name] = {
                "instance": instance,
                "start_callback": start_callback,
                "stop_callback": stop_callback,
                "running": False,
                "started_at": None,
                "stopped_at": None,
            }
        logger.info(f"📋 Engine registered: {self.DISPLAY_NAMES.get(name, name)}")

    # ─── Lifecycle Control ────────────────────────────────────

    def start_engine(self, name: str) -> Tuple[bool, str]:
        """
        Start a specific engine by name.
        Returns (success: bool, message: str).
        """
        if name not in self.VALID_ENGINES:
            return False, f"Unknown engine '{name}'. Valid: {', '.join(sorted(self.VALID_ENGINES))}"

        with _registry_lock:
            entry = self._engines.get(name)
            if not entry:
                return False, f"Engine '{name}' is not registered. It may not be available in this deployment."

            if entry["running"]:
                return True, f"{self.DISPLAY_NAMES[name]} is already running."

            # Execute start callback
            callback = entry.get("start_callback")
            if callback:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Failed to start {name} engine: {e}")
                    return False, f"Failed to start {self.DISPLAY_NAMES[name]}: {str(e)}"

            entry["running"] = True
            entry["started_at"] = time.time()
            entry["stopped_at"] = None
            self._active_set.add(name)

        logger.info(f"▶️ Engine started: {self.DISPLAY_NAMES[name]}")
        return True, f"✅ {self.DISPLAY_NAMES[name]} started successfully."

    def stop_engine(self, name: str) -> Tuple[bool, str]:
        """
        Stop a specific engine by name.
        Returns (success: bool, message: str).
        """
        if name not in self.VALID_ENGINES:
            return False, f"Unknown engine '{name}'. Valid: {', '.join(sorted(self.VALID_ENGINES))}"

        with _registry_lock:
            entry = self._engines.get(name)
            if not entry:
                return False, f"Engine '{name}' is not registered."

            if not entry["running"]:
                return True, f"{self.DISPLAY_NAMES[name]} is already stopped."

            # Execute stop callback
            callback = entry.get("stop_callback")
            if callback:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Failed to stop {name} engine: {e}")
                    return False, f"Failed to stop {self.DISPLAY_NAMES[name]}: {str(e)}"

            entry["running"] = False
            entry["stopped_at"] = time.time()
            self._active_set.discard(name)

        logger.info(f"⏹️ Engine stopped: {self.DISPLAY_NAMES[name]}")
        return True, f"🛑 {self.DISPLAY_NAMES[name]} stopped."

    def mark_running(self, name: str) -> None:
        """Mark an engine as running without invoking callback (for engines started externally)."""
        with _registry_lock:
            entry = self._engines.get(name)
            if entry:
                entry["running"] = True
                entry["started_at"] = time.time()
                entry["stopped_at"] = None
                self._active_set.add(name)

    def mark_stopped(self, name: str) -> None:
        """Mark an engine as stopped without invoking callback."""
        with _registry_lock:
            entry = self._engines.get(name)
            if entry:
                entry["running"] = False
                entry["stopped_at"] = time.time()
                self._active_set.discard(name)

    # ─── Status Queries ───────────────────────────────────────

    def is_running(self, name: str) -> bool:
        """Check if a specific engine is currently running."""
        with _registry_lock:
            entry = self._engines.get(name)
            return entry["running"] if entry else False

    def get_running_engines(self) -> List[str]:
        """Get list of all currently running engine names."""
        with _registry_lock:
            return [name for name, entry in self._engines.items() if entry["running"]]

    def get_status(self) -> Dict[str, Any]:
        """
        Get full status of all registered engines.
        Returns a dictionary suitable for JSON serialization.
        """
        with _registry_lock:
            result = {}
            for name in self.VALID_ENGINES:
                entry = self._engines.get(name)
                if entry:
                    result[name] = {
                        "display_name": self.DISPLAY_NAMES[name],
                        "registered": True,
                        "running": entry["running"],
                        "started_at": entry["started_at"],
                        "stopped_at": entry["stopped_at"],
                    }
                else:
                    result[name] = {
                        "display_name": self.DISPLAY_NAMES[name],
                        "registered": False,
                        "running": False,
                        "started_at": None,
                        "stopped_at": None,
                    }
            return result

    def get_status_text(self) -> str:
        """Get a human-readable status summary string."""
        status = self.get_status()
        lines = ["📊 **Engine Status:**"]
        for name in sorted(self.VALID_ENGINES):
            info = status[name]
            if not info["registered"]:
                icon = "⚪"
                state = "Not Registered"
            elif info["running"]:
                icon = "🟢"
                state = "Running"
            else:
                icon = "🔴"
                state = "Stopped"
            lines.append(f"  {icon} {info['display_name']}: {state}")
        return "\n".join(lines)

    # ─── Bulk Operations ──────────────────────────────────────

    def start_engines(self, names: List[str]) -> Dict[str, str]:
        """Start multiple engines. Returns {name: message}."""
        results = {}
        for name in names:
            _, msg = self.start_engine(name)
            results[name] = msg
        return results

    def stop_engines(self, names: List[str]) -> Dict[str, str]:
        """Stop multiple engines. Returns {name: message}."""
        results = {}
        for name in names:
            _, msg = self.stop_engine(name)
            results[name] = msg
        return results

    def start_all(self) -> Dict[str, str]:
        """Start all registered engines."""
        return self.start_engines(list(self._engines.keys()))

    def stop_all(self) -> Dict[str, str]:
        """Stop all running engines."""
        return self.stop_engines(self.get_running_engines())


# ─── Module-level Singleton ──────────────────────────────────
engine_registry = EngineRegistry()
