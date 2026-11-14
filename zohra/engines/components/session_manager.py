"""
╔══════════════════════════════════════════════════════════════╗
║          INDIAN MARKET ENGINE - SESSION MANAGER              ║
║     Tracks market session states and enforces trading rules   ║
╚══════════════════════════════════════════════════════════════╝

The Session Manager handles:
- Market session state tracking (PRE_OPEN, REGULAR, CLOSING, CLOSED)
- Session schedule retrieval and maintenance
- Session transition event broadcasting
- Session-specific trading rule enforcement
- Holiday and special session handling
"""

import asyncio
import logging
from datetime import datetime, time, date, timedelta
from enum import Enum
from typing import Dict, List, Callable, Optional

from ...brokers.interfaces import UnifiedBrokerAdapter
from ..config import EngineConfig
from ..models import SessionTransition, MarketSession

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages market session state and transitions.
    
    Tracks NSE/BSE market sessions and enforces session-specific trading rules.
    Provides session transition events to all subscribers.
    """
    
    def __init__(self, broker: UnifiedBrokerAdapter, config: EngineConfig):
        self.broker = broker
        self.config = config
        self.current_session = MarketSession.CLOSED
        self.session_schedule: Dict[str, Dict] = {}
        self.subscribers: List[Callable] = []
        self.holidays: List[date] = []
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Default Indian market session times (IST)
        self.default_schedule = {
            "pre_open": {"start": "09:00", "end": "09:15"},
            "regular": {"start": "09:15", "end": "15:30"},
            "closing": {"start": "15:30", "end": "15:40"},
            "closed": {"start": "15:40", "end": "09:00"}  # Next day
        }
        
    async def initialize(self) -> None:
        """Load session schedule and initialize current session state."""
        try:
            # Try to get session schedule from broker
            # If not available, use default schedule
            self.session_schedule = await self._load_session_schedule()
            
            # Load holiday calendar
            await self._load_holidays()
            
            # Determine current session
            await self._update_session_state()
            
            # Start session monitor loop
            self._monitor_task = asyncio.create_task(self._session_monitor_loop())
            
            logger.info(f"Session Manager initialized - Current session: {self.current_session.value}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Session Manager: {e}")
            # Use default schedule as fallback
            self.session_schedule = self.default_schedule
            await self._update_session_state()
            self._monitor_task = asyncio.create_task(self._session_monitor_loop())
    
    async def stop(self) -> None:
        """Stop the session manager."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Session Manager stopped")
    
    async def _load_session_schedule(self) -> Dict[str, Dict]:
        """Load session schedule from broker or external source."""
        # In a real implementation, this might query an API for current market hours
        # For now, return the default Indian market schedule
        logger.info("Loading session schedule (using default Indian market hours)")
        return self.default_schedule
    
    async def _load_holidays(self) -> None:
        """Load holiday calendar for market closures."""
        # In a real implementation, this would fetch holiday calendar from NSE/BSE
        # For now, we'll use a basic list of known holidays
        current_year = datetime.now().year
        
        # Sample holidays for Indian markets (this should be fetched from official sources)
        known_holidays = [
            date(current_year, 1, 26),   # Republic Day
            date(current_year, 8, 15),   # Independence Day  
            date(current_year, 10, 2),   # Gandhi Jayanti
            # Add more holidays as needed
        ]
        
        self.holidays = known_holidays
        logger.info(f"Loaded {len(self.holidays)} market holidays for {current_year}")
    
    async def _update_session_state(self) -> None:
        """Determine and update current session based on time and date."""
        now = datetime.now()
        current_time = now.time()
        current_date = now.date()
        
        # Check if today is a holiday
        if self._is_holiday(current_date):
            new_session = MarketSession.CLOSED
        # Check if it's a weekend (Saturday = 5, Sunday = 6)
        elif now.weekday() in [5, 6]:
            new_session = MarketSession.CLOSED
        # Check time ranges for trading sessions
        else:
            new_session = self._get_session_from_time(current_time)
        
        # Trigger transition if session changed
        if new_session != self.current_session:
            await self._transition_session(new_session)
    
    def _get_session_from_time(self, current_time: time) -> MarketSession:
        """Determine session based on current time."""
        # Convert time strings to time objects for comparison
        pre_open_start = self._parse_time(self.session_schedule["pre_open"]["start"])
        pre_open_end = self._parse_time(self.session_schedule["pre_open"]["end"])
        regular_start = self._parse_time(self.session_schedule["regular"]["start"])
        regular_end = self._parse_time(self.session_schedule["regular"]["end"])
        closing_start = self._parse_time(self.session_schedule["closing"]["start"])
        closing_end = self._parse_time(self.session_schedule["closing"]["end"])
        
        if pre_open_start <= current_time < pre_open_end:
            return MarketSession.PRE_OPEN
        elif regular_start <= current_time < regular_end:
            return MarketSession.REGULAR
        elif closing_start <= current_time < closing_end:
            return MarketSession.CLOSING
        else:
            return MarketSession.CLOSED
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string (HH:MM) to time object."""
        try:
            hour, minute = map(int, time_str.split(':'))
            return time(hour, minute)
        except ValueError:
            logger.error(f"Invalid time format: {time_str}")
            return time(0, 0)
    
    def _is_holiday(self, check_date: date) -> bool:
        """Check if given date is a market holiday."""
        return check_date in self.holidays
    
    async def _transition_session(self, new_session: MarketSession) -> None:
        """Handle session state transition."""
        previous_session = self.current_session
        
        transition = SessionTransition(
            previous_session=previous_session,
            current_session=new_session,
            transition_time=datetime.now(),
            next_transition_time=self._get_next_transition_time()
        )
        
        logger.info(f"📈 Market session transition: {previous_session.value} → {new_session.value}")
        
        self.current_session = new_session
        
        # Broadcast transition event to all subscribers
        for subscriber in self.subscribers:
            try:
                if asyncio.iscoroutinefunction(subscriber):
                    await subscriber(transition)
                else:
                    subscriber(transition)
            except Exception as e:
                logger.error(f"Session transition notification failed: {e}")
    
    def _get_next_transition_time(self) -> Optional[datetime]:
        """Calculate the next session transition time."""
        now = datetime.now()
        
        # Get all transition times for today
        transitions = []
        
        for session_name, schedule in self.session_schedule.items():
            if session_name == "closed":
                continue  # Skip closed as it spans midnight
                
            start_time = self._parse_time(schedule["start"])
            transitions.append((start_time, session_name))
        
        # Sort transitions by time
        transitions.sort(key=lambda x: x[0])
        
        # Find next transition
        current_time = now.time()
        for trans_time, session_name in transitions:
            if trans_time > current_time:
                # Found next transition today
                return now.replace(
                    hour=trans_time.hour,
                    minute=trans_time.minute,
                    second=0,
                    microsecond=0
                )
        
        # Next transition is tomorrow's first session
        tomorrow = now + timedelta(days=1)
        first_trans_time, _ = transitions[0]
        return tomorrow.replace(
            hour=first_trans_time.hour,
            minute=first_trans_time.minute,
            second=0,
            microsecond=0
        )
    
    def subscribe_transitions(self, callback: Callable) -> None:
        """Subscribe to session transition events."""
        self.subscribers.append(callback)
        logger.debug(f"Added session transition subscriber: {callback.__name__}")
    
    def unsubscribe_transitions(self, callback: Callable) -> None:
        """Unsubscribe from session transition events."""
        if callback in self.subscribers:
            self.subscribers.remove(callback)
            logger.debug(f"Removed session transition subscriber: {callback.__name__}")
    
    def is_trading_allowed(self, order_type: str) -> bool:
        """Check if trading is allowed for given order type in current session."""
        if self.current_session == MarketSession.CLOSED:
            return False
        elif self.current_session == MarketSession.PRE_OPEN:
            # Only limit orders allowed in pre-open
            return order_type.upper() in ["LIMIT", "STOP_LIMIT"]
        elif self.current_session in [MarketSession.REGULAR, MarketSession.CLOSING]:
            return True
        return False
    
    def get_session_info(self) -> Dict:
        """Get current session information."""
        return {
            "current_session": self.current_session.value,
            "session_schedule": self.session_schedule,
            "next_transition": self._get_next_transition_time().isoformat() if self._get_next_transition_time() else None,
            "is_holiday": self._is_holiday(date.today()),
            "trading_allowed": {
                "MARKET": self.is_trading_allowed("MARKET"),
                "LIMIT": self.is_trading_allowed("LIMIT"),
                "STOP": self.is_trading_allowed("STOP"),
                "STOP_LIMIT": self.is_trading_allowed("STOP_LIMIT")
            }
        }
    
    async def _session_monitor_loop(self) -> None:
        """Continuously monitor for session transitions."""
        while True:
            try:
                # Check for session transitions every 30 seconds
                await asyncio.sleep(30)
                await self._update_session_state()
                
            except asyncio.CancelledError:
                logger.info("Session monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Session monitor loop error: {e}")
                # Continue monitoring despite errors