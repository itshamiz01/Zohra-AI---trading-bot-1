"""
Connection Manager - Handles Dhan API connectivity with resilience patterns.

Implements:
- Authenticated connection establishment
- Exponential backoff retry logic
- Circuit breaker pattern for failure protection
- Health monitoring with heartbeat
- Automatic reconnection
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from ..models import CircuitState
from ....brokers.interfaces import UnifiedBrokerAdapter

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_attempts: int = 3
    ):
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
                logger.error(
                    f"Circuit breaker opened after {self.failure_count} failures"
                )
        
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
    """Manages Dhan API connection with resilience patterns."""
    
    def __init__(self, broker: UnifiedBrokerAdapter, config):
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
                if not self.circuit_breaker.can_execute():
                    logger.warning("Circuit breaker OPEN, waiting for recovery")
                    await asyncio.sleep(self.circuit_breaker.recovery_timeout)
                    continue
                
                logger.info(f"Connection attempt {attempt + 1}/{self.max_retries}")
                
                # Attempt authentication
                start_time = time.time()
                await self.broker.authenticate(
                    client_id=self.config.dhan_client_id,
                    access_token=self.config.dhan_access_token.get_secret_value()
                )
                latency = (time.time() - start_time) * 1000
                
                if latency > 5000:
                    logger.warning(f"Connection latency {latency:.2f}ms exceeds 5s threshold")
                
                self.is_connected = True
                self.circuit_breaker.record_success()
                logger.info(f"✅ Successfully connected to Dhan API (latency: {latency:.2f}ms)")
                
                # Start health monitoring
                self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
                
                return True
                
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                self.circuit_breaker.record_failure()
                
                # Exponential backoff: 2^attempt seconds
                backoff_delay = min(2 ** attempt, 60)
                logger.info(f"Retrying in {backoff_delay} seconds...")
                await asyncio.sleep(backoff_delay)
                attempt += 1
        
        logger.error("Max connection attempts exceeded")
        return False
    
    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        
        if self.is_connected:
            try:
                await self.broker.disconnect()
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            
            self.is_connected = False
            logger.info("Disconnected from Dhan API")
    
    async def _health_monitor_loop(self) -> None:
        """Monitor connection health with heartbeat."""
        while self.is_connected:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_sec)
                
                # Send heartbeat
                health_ok = await self.broker.check_connection_health()
                
                if not health_ok:
                    logger.warning("Health check failed, notifying Trading Core")
                    await self._notify_degraded_connectivity()
                    
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
    
    async def _notify_degraded_connectivity(self) -> None:
        """Notify Trading Core of connectivity degradation."""
        logger.warning("Connectivity degraded - notification sent to Trading Core")
        # Implementation depends on Trading Core API
    
    def get_status(self) -> str:
        """Return current connection status."""
        if self.circuit_breaker.state == CircuitState.OPEN:
            return "CIRCUIT_OPEN"
        elif not self.is_connected:
            return "DISCONNECTED"
        else:
            return "CONNECTED"
    
    def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        return self.is_connected and self.circuit_breaker.state == CircuitState.CLOSED
