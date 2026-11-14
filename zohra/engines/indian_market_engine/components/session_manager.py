"""
Session Manager - Tracks market session states and enforces session rules.

Implements:
- Market session state tracking (PRE_OPEN, REGULAR, CLOSING, CLOSED)
- Session transition detection and broadcasting
- Session-specific trading rule enforcement
- Holiday schedule handling
"""

import asyncio
import logging
from datetime import datetime, time as datetime_time
from typing import Dict, List, Callable, Optional

from ..models import MarketSession, SessionTransition
from ....brokers.interfaces import UnifiedBrokerAdapter

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages market session state and transitions."""
    
    def __init__(self, broker: UnifiedBrokerAdapter, config):
        self.broker = broker
        self.config = config
        self.current_session = MarketSession.CLOSED
        self.session_schedule: Dict[str, Dict] = {}
        self.subscribers: List[Callable] = []
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> None:
        """Load session schedule from Dhan adapter."""
        try:
            self.session_schedule = await self.broker.get_session_schedule()
            logger.info("Session schedule loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load session schedule: {e}, using defaults")
            self._set_default_schedule()
        
        # Determine current session
        await self._update_session_state()
        
        # Start session monitor loop
        self._monitor_task = asyncio.create_task(self._session_monitor_loop())
        logger.info(f"Session manager initialized - Current session: {self.current_session.value}")
    
    def _set_default_schedule(self) -> None:
        """Set default NSE schedule."""
        self.session_schedule = {
            "pre_open": {"start": "09:00", "end": "09:15"},
            "regular": {"start": "09:15", "end": "15:30"},
            "closing": {"start": "15:30", "end": "15:40"},
        }
    
    async def _update_session_state(self) -> None:
        """Determine and update current session based on time."""
        now = datetime.now()
        current_time = now.time()
        
        # Check if holiday
        if self._is_holiday(now.date()):
            new_session = MarketSession.CLOSED
        # Check time ranges
        elif self._time_in_range(current_time, "09:00", "09:15"):
            new_session = MarketSession.PRE_OPEN
        elif self._time_in_range(current_time, "09:15", "15:30"):
            new_session = MarketSession.REGULAR
        elif self._time_in_range(current_time, "15:30", "15:40"):
            new_session = MarketSession.CLOSING
        else:
            new_session = MarketSession.CLOSED
        
        if new_session != self.current_session:
            await self._transition_session(new_session)
    
    async def _transition_session(self, new_session: MarketSession) -> None:
        """Handle session state transition."""
        transition = SessionTransition(
            previous_session=self.current_session,
            current_session=new_session,
            transition_time=datetime.now(),
            next_transition_time=self._get_next_transition_time()
        )
        
        logger.info(f"📍 Session transition: {self.current_session.value} → {new_session.value}")
        
        self.current_session = new_session
        
        # Broadcast transition event to all subscribers
        for subscriber in self.subscribers:
            try:
                await subscriber(transition)
            except Exception as e:
                logger.error(f"Session transition notification failed: {e}")
    
    def subscribe_transitions(self, callback: Callable) -> None:
        """Subscribe to session transition events."""
        self.subscribers.append(callback)
        logger.debug(f"Added session transition subscriber (total: {len(self.subscribers)})")
    
    def is_trading_allowed(self, order_type: str) -> bool:
        """Check if trading is allowed for given order type in current session."""
        if self.current_session == MarketSession.CLOSED:
            return False
        elif self.current_session == MarketSession.PRE_OPEN:
            # Only limit orders allowed in pre-open
            return order_type in ["LIMIT", "STOP_LIMIT"]
        elif self.current_session in [MarketSession.REGULAR, MarketSession.CLOSING]:
            return True
        return False
    
    async def _session_monitor_loop(self) -> None:
        """Monitor and update session state periodically."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._update_session_state()
            except Exception as e:
                logger.error(f"Session monitor error: {e}")
    
    def _time_in_range(self, current: datetime_time, start_str: str, end_str: str) -> bool:
        """Check if current time is within range."""
        start = datetime.strptime(start_str, "%H:%M").time()
        end = datetime.strptime(end_str, "%H:%M").time()
        return start <= current <= end
    
    def _is_holiday(self, date) -> bool:
        """Check if date is a holiday."""
        # Simple implementation - can be enhanced with actual holiday calendar
        return date.weekday() >= 5  # Saturday=5, Sunday=6
    
    def _get_next_transition_time(self) -> Optional[datetime]:
        """Calculate next session transition time."""
        # Simplified implementation
        now = datetime.now()
        current_time = now.time()
        
        if current_time < datetime.strptime("09:00", "%H:%M").time():
            return now.replace(hour=9, minute=0, second=0)
        elif current_time < datetime.strptime("09:15", "%H:%M").time():
            return now.replace(hour=9, minute=15, second=0)
        elif current_time < datetime.strptime("15:30", "%H:%M").time():
            return now.replace(hour=15, minute=30, second=0)
        elif current_time < datetime.strptime("15:40", "%H:%M").time():
            return now.replace(hour=15, minute=40, second=0)
        else:
            # Next day 09:00
            return None
