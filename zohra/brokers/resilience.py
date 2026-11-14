"""
╔══════════════════════════════════════════════════════════════╗
║      MARKET ABSTRACTION LAYER — RESILIENCE ENGINE           ║
║  Retry, circuit breaker, and auto-reconnection              ║
╚══════════════════════════════════════════════════════════════╝

Provides:
  - RetryConfig: configurable retry parameters
  - @with_retry: decorator for automatic retries with exponential backoff
  - CircuitBreaker: circuit breaker pattern (CLOSED → OPEN → HALF_OPEN)
  - @with_circuit_breaker: decorator for circuit breaker wrapping
  - ReconnectionManager: monitors and auto-reconnects broker connections
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type

logger = logging.getLogger("zohra.resilience")


# ════════════════════════════════════════════════════════════════
#  Retry Configuration
# ════════════════════════════════════════════════════════════════

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 0.5          # seconds
    max_delay: float = 30.0          # seconds
    backoff_factor: float = 2.0      # exponential multiplier
    retryable_exceptions: tuple = (Exception,)
    # Non-retryable error codes (e.g., MT5 error 10027 = AutoTrading disabled)
    non_retryable_codes: Set[int] = field(default_factory=lambda: {10027})

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt (0-indexed)."""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)


# Default configs for different operation types
RETRY_FAST = RetryConfig(max_retries=2, base_delay=0.2, max_delay=2.0)
RETRY_STANDARD = RetryConfig(max_retries=3, base_delay=0.5, max_delay=10.0)
RETRY_AGGRESSIVE = RetryConfig(max_retries=5, base_delay=1.0, max_delay=30.0)
RETRY_CONNECTION = RetryConfig(max_retries=5, base_delay=2.0, max_delay=60.0, backoff_factor=3.0)


# ════════════════════════════════════════════════════════════════
#  @with_retry Decorator
# ════════════════════════════════════════════════════════════════

def with_retry(config: RetryConfig = None, operation_name: str = None):
    """
    Decorator for automatic retries with exponential backoff.

    Usage:
        @with_retry(RETRY_STANDARD, "get_tick")
        def get_tick(self, symbol: str) -> dict:
            ...

        @with_retry()  # uses RETRY_STANDARD
        def some_method(self):
            ...
    """
    if config is None:
        config = RETRY_STANDARD

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            op = operation_name or func.__name__
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    # Check for non-retryable error codes
                    error_code = getattr(e, "code", None)
                    if error_code and error_code in config.non_retryable_codes:
                        logger.error(
                            f"[Retry] {op}: Non-retryable error code {error_code} — "
                            f"aborting: {e}"
                        )
                        raise

                    if attempt < config.max_retries:
                        delay = config.get_delay(attempt)
                        logger.warning(
                            f"[Retry] {op}: Attempt {attempt + 1}/{config.max_retries + 1} "
                            f"failed ({type(e).__name__}: {e}). "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry] {op}: All {config.max_retries + 1} attempts exhausted. "
                            f"Final error: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


# ════════════════════════════════════════════════════════════════
#  Circuit Breaker
# ════════════════════════════════════════════════════════════════

class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation
    OPEN = "OPEN"            # Blocking all calls
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker pattern for broker connections.

    States:
      CLOSED   → Normal. Track failures. If failures >= threshold → OPEN.
      OPEN     → Block all calls. After recovery_timeout → HALF_OPEN.
      HALF_OPEN → Allow one test call. If success → CLOSED. If fail → OPEN.
    """

    def __init__(self, name: str = "default",
                 failure_threshold: int = 5,
                 recovery_timeout: float = 60.0,
                 half_open_max_calls: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(
                        f"[CircuitBreaker:{self.name}] OPEN → HALF_OPEN "
                        f"(recovery timeout elapsed)"
                    )
            return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        f"[CircuitBreaker:{self.name}] HALF_OPEN → CLOSED (recovered)"
                    )
            else:
                self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[CircuitBreaker:{self.name}] HALF_OPEN → OPEN "
                    f"(test call failed)"
                )
            elif self._failure_count >= self.failure_threshold:
                if self._state == CircuitState.CLOSED:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        f"[CircuitBreaker:{self.name}] CLOSED → OPEN "
                        f"(failure threshold {self.failure_threshold} reached)"
                    )

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        state = self.state  # triggers OPEN → HALF_OPEN check
        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
        else:  # OPEN
            return False

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            logger.info(f"[CircuitBreaker:{self.name}] Manual reset → CLOSED")

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure": self._last_failure_time,
        }


# ════════════════════════════════════════════════════════════════
#  @with_circuit_breaker Decorator
# ════════════════════════════════════════════════════════════════

class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and blocking calls."""
    pass


def with_circuit_breaker(breaker: CircuitBreaker):
    """
    Decorator that wraps a function with circuit breaker logic.

    Usage:
        cb = CircuitBreaker("mt5_orders", failure_threshold=3)

        @with_circuit_breaker(cb)
        def place_order(self, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not breaker.allow_request():
                raise CircuitOpenError(
                    f"Circuit breaker '{breaker.name}' is {breaker.state.value}. "
                    f"Call blocked to prevent cascading failures."
                )
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except CircuitOpenError:
                raise
            except Exception as e:
                breaker.record_failure()
                raise

        # Expose breaker on the wrapper for introspection
        wrapper.circuit_breaker = breaker
        return wrapper
    return decorator


# ════════════════════════════════════════════════════════════════
#  Reconnection Manager
# ════════════════════════════════════════════════════════════════

class ReconnectionManager:
    """
    Monitors broker connections and triggers automatic reconnection.

    Usage:
        recon = ReconnectionManager()
        recon.register("mt5", mt5_adapter)
        recon.start()  # starts background monitoring thread
    """

    def __init__(self, check_interval: float = 30.0,
                 max_reconnect_attempts: int = 10):
        self._adapters: Dict[str, Any] = {}
        self._check_interval = check_interval
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_counts: Dict[str, int] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register(self, name: str, adapter: Any) -> None:
        """Register a broker adapter for monitoring."""
        self._adapters[name] = adapter
        self._reconnect_counts[name] = 0
        logger.info(f"[Reconnect] Registered adapter: {name}")

    def unregister(self, name: str) -> None:
        """Unregister a broker adapter."""
        self._adapters.pop(name, None)
        self._reconnect_counts.pop(name, None)

    def start(self) -> None:
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="broker-reconnect"
        )
        self._thread.start()
        logger.info(
            f"[Reconnect] Monitor started (interval={self._check_interval}s)"
        )

    def stop(self) -> None:
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("[Reconnect] Monitor stopped")

    def _monitor_loop(self) -> None:
        """Background loop that checks connections periodically."""
        while self._running:
            for name, adapter in list(self._adapters.items()):
                try:
                    if not adapter.is_connected():
                        count = self._reconnect_counts.get(name, 0)
                        if count < self._max_reconnect_attempts:
                            logger.warning(
                                f"[Reconnect] {name}: Connection lost. "
                                f"Attempting reconnect ({count + 1}/"
                                f"{self._max_reconnect_attempts})..."
                            )
                            success = adapter.reconnect() if hasattr(adapter, "reconnect") else adapter.connect()
                            if success:
                                self._reconnect_counts[name] = 0
                                logger.info(
                                    f"[Reconnect] {name}: Reconnected successfully!"
                                )
                            else:
                                self._reconnect_counts[name] = count + 1
                                logger.error(
                                    f"[Reconnect] {name}: Reconnect failed "
                                    f"({count + 1}/{self._max_reconnect_attempts})"
                                )
                        else:
                            logger.critical(
                                f"[Reconnect] {name}: Max reconnect attempts "
                                f"({self._max_reconnect_attempts}) exhausted!"
                            )
                    else:
                        # Reset counter on successful heartbeat
                        self._reconnect_counts[name] = 0
                except Exception as e:
                    logger.error(f"[Reconnect] {name}: Monitor error: {e}")

            time.sleep(self._check_interval)

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get reconnection status for all adapters."""
        status = {}
        for name, adapter in self._adapters.items():
            connected = False
            try:
                connected = adapter.is_connected()
            except Exception:
                pass
            status[name] = {
                "connected": connected,
                "reconnect_attempts": self._reconnect_counts.get(name, 0),
                "max_attempts": self._max_reconnect_attempts,
            }
        return status


# ════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════

reconnection_manager = ReconnectionManager()
