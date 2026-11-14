"""
╔══════════════════════════════════════════════════════════════╗
║         INDIAN MARKET ENGINE - CONNECTION MANAGER            ║
║   Manages Dhan API connection with resilience patterns       ║
╚══════════════════════════════════════════════════════════════╝

The Connection Manager handles:
- Authenticated connection establishment with Dhan API
- Connection health monitoring with 30-second heartbeat
- Automatic reconnection with exponential backoff (up to 5 attempts)
- Circuit breaker pattern for failure protection
- Connection status notification to Trading Core
"""

import asyncio
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Optional

from ...brokers.interfaces import UnifiedBrokerAdapter
from ..config import EngineConfig

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Blocking calls
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30, half_open_attempts: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_attempts = half_open_attempts
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_success_count = 0
    
    def record_success(self) -> None:
        """Record successful operation."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_success_count += 1
            
            if self.half_open_success_count >= self.half_open_attempts:
                # Recovery successful, close circuit
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_success_count = 0
                logger.info("Circuit breaker closed after successful recovery")
        
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(f"Circuit breaker opened after {self.failure_count} failures")
        
        elif self.state == CircuitState.HALF_OPEN:
            # Recovery attempt failed, reopen circuit
            self.state = CircuitState.OPEN
            self.half_open_success_count = 0
            logger.warning("Circuit breaker reopened after failed recovery attempt")
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        if self.state == CircuitState.CLOSED:
            return True
        
        elif self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker entering HALF_OPEN state for recovery probe")
                    return True
            
            return False
        
        elif self.state == CircuitState.HALF_OPEN:
            return True
        
        return False


class ConnectionManager:
    """
    Manages Dhan API connection with resilience patterns.
    
    Implements exponential backoff retry logic and circuit breaker pattern
    to handle connection failures gracefully while maintaining system stability.
    """
    
    def __init__(self, broker: UnifiedBrokerAdapter, config: EngineConfig):
        self.broker = broker
        self.config = config
        self.is_connected = False
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout_sec,
            half_open_attempts=config.circuit_breaker_half_open_attempts
        )
        self.retry_count = 0
        self.max_retries = config.max_connection_retries
        self._health_monitor_task: Optional[asyncio.Task] = None
        
    async def connect(self) -> bool:
        """
        Establish authenticated connection with retry logic.
        
        Returns:
            True if connection successful, False otherwise
        """
        attempt = 0
        
        while attempt < self.max_retries:
            try:
                if self.circuit_breaker.state == CircuitState.OPEN:
                    logger.warning("Circuit breaker OPEN, waiting for recovery")
                    await asyncio.sleep(self.circuit_breaker.recovery_timeout)
                    continue
                
                if not self.circuit_breaker.can_execute():
                    logger.warning("Circuit breaker blocking connection attempt")
                    continue
                
                logger.info(f"Connection attempt {attempt + 1}/{self.max_retries}")
                
                # Attempt connection
                start_time = time.time()
                connected = self.broker.connect()
                latency = (time.time() - start_time) * 1000
                
                if connected:
                    if latency > 5000:
                        logger.warning(f"Connection latency {latency:.1f}ms exceeds 5s threshold")
                    
                    self.is_connected = True
                    self.circuit_breaker.record_success()
                    logger.info(f"✅ Successfully connected to Dhan API (latency: {latency:.1f}ms)")
                    
                    # Start health monitoring
                    self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
                    
                    return True
                else:
                    raise ConnectionError("Broker connection failed")
                
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                self.circuit_breaker.record_failure()
                
                # Exponential backoff: 2^attempt seconds, max 60s
                backoff_delay = min(2 ** attempt, 60)
                logger.info(f"Retrying in {backoff_delay} seconds...")
                await asyncio.sleep(backoff_delay)
                attempt += 1
        
        logger.error(f"❌ Failed to connect after {self.max_retries} attempts")
        return False
    
    async def disconnect(self) -> None:
        """Gracefully disconnect from Dhan API."""
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        
        if self.is_connected and self.broker:
            self.broker.disconnect()
            self.is_connected = False
            logger.info("✅ Disconnected from Dhan API")
    
    def get_status(self) -> str:
        """Return current connection status."""
        if self.circuit_breaker.state == CircuitState.OPEN:
            return "CIRCUIT_OPEN"
        elif self.circuit_breaker.state == CircuitState.HALF_OPEN:
            return "CIRCUIT_HALF_OPEN"
        elif not self.is_connected:
            return "DISCONNECTED"
        else:
            return "CONNECTED"
    
    def get_detailed_status(self) -> dict:
        """Return detailed connection status information."""
        return {
            "connected": self.is_connected,
            "circuit_state": self.circuit_breaker.state.value,
            "failure_count": self.circuit_breaker.failure_count,
            "last_failure": self.circuit_breaker.last_failure_time.isoformat() if self.circuit_breaker.last_failure_time else None,
            "broker_name": self.broker.name if self.broker else None
        }
    
    async def _health_monitor_loop(self) -> None:
        """Monitor connection health with 30-second heartbeat."""
        while self.is_connected:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_sec)
                
                # Perform health check
                health = self.broker.health_check()
                
                if health.get('status') != 'healthy':
                    logger.warning(f"Health check failed: {health}")
                    await self._notify_degraded_connectivity()
                else:
                    logger.debug("Connection health check passed")
                    
            except asyncio.CancelledError:
                logger.info("Health monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                # Consider this a connection degradation
                await self._notify_degraded_connectivity()
    
    async def _notify_degraded_connectivity(self) -> None:
        """Notify Trading Core of degraded connectivity status."""
        logger.warning("🔶 Notifying Trading Core of degraded connectivity")
        # This would integrate with the event system or direct Trading Core notification
        # For now, we'll log it - the integration bridge would handle actual notification
    
    async def test_connection(self) -> bool:
        """Test current connection without side effects."""
        if not self.is_connected:
            return False
        
        try:
            health = self.broker.health_check()
            return health.get('status') == 'healthy'
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False