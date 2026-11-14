"""
Event Publisher - Internal pub-sub event communication system.

Implements:
- Event subscription and publishing
- Event queuing for unavailable subscribers
- Event replay capability
"""

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Callable, Any, Deque, Optional

logger = logging.getLogger(__name__)


class EventPublisher:
    """Broadcasts system events using pub-sub pattern."""
    
    def __init__(self, max_queue_size: int = 1000):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_queue: Deque[Dict[str, Any]] = deque(maxlen=max_queue_size)
        
    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to specific event type."""
        self.subscribers[event_type].append(callback)
        logger.debug(f"Subscriber added for {event_type} (total: {len(self.subscribers[event_type])})")
    
    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from event type."""
        if event_type in self.subscribers:
            try:
                self.subscribers[event_type].remove(callback)
                logger.debug(f"Subscriber removed from {event_type}")
            except ValueError:
                logger.warning(f"Callback not found in {event_type} subscribers")
    
    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish event to all subscribers."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add to queue for replay capability
        self.event_queue.append(event)
        
        # Notify all subscribers
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Event handler error for {event_type}: {e}")
    
    def get_recent_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get recent events for replay."""
        events = list(self.event_queue)
        
        if event_type:
            events = [e for e in events if e['type'] == event_type]
        
        return events[-limit:]
    
    def get_subscriber_count(self, event_type: str) -> int:
        """Get number of subscribers for event type."""
        return len(self.subscribers.get(event_type, []))
