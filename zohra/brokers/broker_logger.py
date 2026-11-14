"""
╔══════════════════════════════════════════════════════════════╗
║      MARKET ABSTRACTION LAYER — BROKER INTERACTION LOGGER   ║
║  Structured logging for every broker API call               ║
╚══════════════════════════════════════════════════════════════╝

Generates structured logs for every broker interaction including:
timestamp, broker, operation, request, response, latency, errors, retries.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("zohra.broker_logger")


# ════════════════════════════════════════════════════════════════
#  Interaction Log Entry
# ════════════════════════════════════════════════════════════════

@dataclass
class BrokerInteractionLog:
    """Structured log entry for a single broker API call."""
    timestamp: str = ""
    broker: str = ""
    operation: str = ""
    request: Dict[str, Any] = field(default_factory=dict)
    response: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    retries: int = 0
    execution_status: str = "OK"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "broker": self.broker,
            "operation": self.operation,
            "request": self.request,
            "response": self.response,
            "latency_ms": round(self.latency_ms, 2),
            "success": self.success,
            "error": self.error,
            "retries": self.retries,
            "execution_status": self.execution_status,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


# ════════════════════════════════════════════════════════════════
#  Broker Logger
# ════════════════════════════════════════════════════════════════

class BrokerLogger:
    """
    Centralized logger for all broker interactions.
    Writes structured JSONL logs and maintains an in-memory buffer.
    """

    def __init__(self, log_dir: str = None, max_buffer: int = 1000):
        self._buffer: List[BrokerInteractionLog] = []
        self._max_buffer = max_buffer
        self._error_counts: Dict[str, int] = {}

        # Determine log file path
        if log_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(base, "logs")
        os.makedirs(log_dir, exist_ok=True)
        self._log_file = os.path.join(log_dir, "broker_interactions.jsonl")

    def log_interaction(self, entry: BrokerInteractionLog) -> None:
        """Log a broker interaction entry."""
        # Buffer
        self._buffer.append(entry)
        if len(self._buffer) > self._max_buffer:
            self._buffer = self._buffer[-self._max_buffer:]

        # Track errors
        if not entry.success:
            key = f"{entry.broker}:{entry.operation}"
            self._error_counts[key] = self._error_counts.get(key, 0) + 1

        # Write to JSONL file
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write broker log: {e}")

        # Also emit to Python logger
        if entry.success:
            logger.debug(
                f"[{entry.broker}] {entry.operation} | "
                f"{entry.latency_ms:.1f}ms | OK"
            )
        else:
            logger.warning(
                f"[{entry.broker}] {entry.operation} | "
                f"{entry.latency_ms:.1f}ms | FAILED: {entry.error}"
            )

    def get_recent_logs(self, count: int = 50,
                        broker: str = None) -> List[Dict[str, Any]]:
        """Get recent interaction logs from buffer."""
        logs = self._buffer
        if broker:
            logs = [l for l in logs if l.broker == broker]
        return [l.to_dict() for l in logs[-count:]]

    def get_error_summary(self) -> Dict[str, int]:
        """Get error counts grouped by broker:operation."""
        return dict(self._error_counts)

    def get_stats(self, broker: str = None) -> Dict[str, Any]:
        """Get aggregate statistics for broker interactions."""
        logs = self._buffer
        if broker:
            logs = [l for l in logs if l.broker == broker]

        if not logs:
            return {"total": 0, "success": 0, "failed": 0, "avg_latency_ms": 0.0}

        total = len(logs)
        success = sum(1 for l in logs if l.success)
        failed = total - success
        avg_latency = sum(l.latency_ms for l in logs) / total if total else 0.0

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate_pct": round((success / total) * 100, 1) if total else 0.0,
            "avg_latency_ms": round(avg_latency, 2),
            "errors": self.get_error_summary(),
        }


# ════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════

broker_logger = BrokerLogger()


# ════════════════════════════════════════════════════════════════
#  Decorator for automatic logging
# ════════════════════════════════════════════════════════════════

def log_broker_call(operation: str = None, include_args: bool = True):
    """
    Decorator that automatically logs broker API calls.

    Usage:
        @log_broker_call("get_tick")
        def get_tick(self, symbol: str) -> dict:
            ...

        @log_broker_call()  # auto-detects operation name from method name
        def open_trade(self, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            op_name = operation or func.__name__
            broker_name = getattr(self, "name", "unknown")

            # Build request summary
            request_data = {}
            if include_args:
                # Capture positional args by parameter name
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())[1:]  # skip 'self'
                for i, param in enumerate(params):
                    if i < len(args):
                        val = args[i]
                        # Don't log huge DataFrames
                        if hasattr(val, "shape"):
                            request_data[param] = f"DataFrame{val.shape}"
                        else:
                            request_data[param] = val
                request_data.update(kwargs)

            start = time.perf_counter()
            error_str = None
            success = True
            result = None

            try:
                result = func(self, *args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_str = f"{type(e).__name__}: {str(e)}"
                raise
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000

                # Build response summary
                response_data = {}
                if result is not None:
                    if isinstance(result, dict):
                        response_data = {k: v for k, v in result.items()
                                         if not isinstance(v, (bytes, memoryview))}
                    elif hasattr(result, "to_dict"):
                        response_data = result.to_dict()
                    elif hasattr(result, "shape"):
                        response_data = {"type": "DataFrame", "shape": str(result.shape)}
                    else:
                        response_data = {"value": str(result)[:200]}

                entry = BrokerInteractionLog(
                    broker=broker_name,
                    operation=op_name,
                    request=_safe_serialize(request_data),
                    response=_safe_serialize(response_data),
                    latency_ms=elapsed_ms,
                    success=success,
                    error=error_str,
                    execution_status="OK" if success else "ERROR",
                )
                broker_logger.log_interaction(entry)

        return wrapper
    return decorator


def _safe_serialize(data: Any) -> Dict[str, Any]:
    """Safely serialize data for logging, handling non-serializable types."""
    if not isinstance(data, dict):
        return {"raw": str(data)[:500]}
    result = {}
    for k, v in data.items():
        try:
            json.dumps(v)
            result[k] = v
        except (TypeError, ValueError):
            result[k] = str(v)[:200]
    return result
