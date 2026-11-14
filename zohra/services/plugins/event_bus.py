# ZOHRA OS — Central Event Bus
import logging
import asyncio
from typing import Dict, List, Callable, Any, Coroutine

logger = logging.getLogger("zohra.plugins.event_bus")

class EventBus:
    """
    Decoupled publish-subscribe event broker.
    Allows core divisions and plugins to communicate asynchronously.
    """
    def __init__(self):
        self.listeners: Dict[str, List[Callable[[Any], Coroutine[Any, Any, None]]]] = {}

    def subscribe(self, event_type: str):
        """Decorator to subscribe a coroutine to a specific event type."""
        def decorator(func: Callable[[Any], Coroutine[Any, Any, None]]):
            if event_type not in self.listeners:
                self.listeners[event_type] = []
            self.listeners[event_type].append(func)
            logger.info(f"Subscribed handler '{func.__name__}' to event: '{event_type}'")
            return func
        return decorator

    async def publish(self, event_type: str, data: Any):
        """Publishes an event to all registered listeners asynchronously."""
        if event_type not in self.listeners:
            logger.debug(f"No listeners registered for event: '{event_type}'")
            return
            
        logger.info(f"Publishing event '{event_type}' to {len(self.listeners[event_type])} listeners.")
        tasks = []
        for listener in self.listeners[event_type]:
            # Launch each listener as an independent async task
            tasks.append(asyncio.create_task(self._safe_execute(listener, event_type, data)))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_execute(self, listener: Callable, event_type: str, data: Any):
        try:
            await listener(data)
        except Exception as e:
            logger.error(f"Error in listener '{listener.__name__}' for event '{event_type}': {e}")
            
    def unsubscribe(self, event_type: str, func: Callable):
        """Removes a listener subscription."""
        if event_type in self.listeners and func in self.listeners[event_type]:
            self.listeners[event_type].remove(func)
            logger.info(f"Unsubscribed handler '{func.__name__}' from event: '{event_type}'")
