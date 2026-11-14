# zohra/event_bus.py
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Any

logger = logging.getLogger("zohra.event_bus")

@dataclass(frozen=True)
class EventEnvelope:
    event_type: str
    payload: Dict[str, Any]
    sequence_id: int
    timestamp: str


class EventBus:
    """
    Decoupled Event Bus supporting async and sync handlers.
    Ensures trading loop remains active even if DB, UI, or AI modules hang or fail.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._sequence_id = 0

    def create_envelope(self, event_type: str, payload: Dict[str, Any]) -> EventEnvelope:
        if not isinstance(payload, dict):
            raise ValueError("Event payload must be an object")
        if event_type == "agent.task.requested":
            missing = {"agent_id", "task_id", "action", "params", "permission_tier"} - payload.keys()
            if missing:
                raise ValueError(f"Missing task fields: {', '.join(sorted(missing))}")
        self._sequence_id += 1
        return EventEnvelope(event_type, dict(payload), self._sequence_id, datetime.now(timezone.utc).isoformat())

    def subscribe(self, event_type: str, callback: Callable):
        """Register a subscriber callback for a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed callback {callback.__name__} to event: {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """Remove a subscriber without disturbing other listeners."""
        callbacks = self._subscribers.get(event_type)
        if not callbacks or callback not in callbacks:
            return False
        callbacks.remove(callback)
        if not callbacks:
            self._subscribers.pop(event_type, None)
        return True

    async def publish(self, event_type: str, data: Any, *, source: str | None = None):
        """Publish an event to all subscribers asynchronously."""
        if source is not None:
            if isinstance(data, dict):
                data = {**data, "source": data.get("source", source)}
            else:
                data = {"data": data, "source": source}
        if event_type not in self._subscribers:
            return
        
        tasks = []
        for callback in self._subscribers[event_type]:
            # Wrap standard sync functions in run_in_executor to avoid blocking the event loop
            if asyncio.iscoroutinefunction(callback):
                tasks.append(self._safe_async_call(callback, data))
            else:
                loop = asyncio.get_running_loop()
                tasks.append(self._safe_sync_call_in_executor(loop, callback, data))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_async_call(self, callback: Callable, data: Any):
        try:
            await callback(data)
        except Exception as e:
            logger.error(f"Error executing async event handler {callback.__name__} for event: {e}", exc_info=True)

    async def _safe_sync_call_in_executor(self, loop: asyncio.AbstractEventLoop, callback: Callable, data: Any):
        try:
            await loop.run_in_executor(None, callback, data)
        except Exception as e:
            logger.error(f"Error executing sync event handler {callback.__name__} in executor: {e}", exc_info=True)

# Central singleton instance
event_bus = EventBus()
