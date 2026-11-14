"""
Data Stream Processor - Manages real-time WebSocket data streaming.

Implements:
- WebSocket connection for real-time tick data
- Tick normalization to StandardTick format (<10ms)
- Buffering with 10,000 message capacity
- Data latency tracking
- Subscription management
- Automatic reconnection
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Set, List, Callable, Dict, Any, Optional

from ....brokers.models import StandardTick
from ....brokers.interfaces import UnifiedBrokerAdapter

logger = logging.getLogger(__name__)


class LatencyTracker:
    """Tracks latency metrics with percentile calculation."""
    
    def __init__(self, max_samples: int = 10000):
        self.samples: deque = deque(maxlen=max_samples)
    
    def record(self, latency_ms: float) -> None:
        """Record latency sample."""
        self.samples.append(latency_ms)
    
    def get_average(self) -> float:
        """Calculate average latency."""
        if not self.samples:
            return 0.0
        return sum(self.samples) / len(self.samples)
    
    def get_percentile(self, percentile: int) -> float:
        """Calculate percentile latency."""
        if not self.samples:
            return 0.0
        
        sorted_samples = sorted(self.samples)
        index = int(len(sorted_samples) * percentile / 100)
        return sorted_samples[min(index, len(sorted_samples) - 1)]
    
    def get_metrics(self) -> Dict:
        """Get all latency metrics."""
        if not self.samples:
            return {
                "count": 0,
                "avg": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "max": 0.0
            }
        
        sorted_samples = sorted(self.samples)
        
        return {
            "count": len(self.samples),
            "avg": self.get_average(),
            "p50": sorted_samples[len(sorted_samples) // 2],
            "p95": self.get_percentile(95),
            "p99": self.get_percentile(99),
            "max": sorted_samples[-1]
        }


class DataStreamProcessor:
    """Processes real-time market data from WebSocket stream."""
    
    def __init__(self, broker: UnifiedBrokerAdapter, config):
        self.broker = broker
        self.config = config
        self.subscribed_instruments: Set[str] = set()
        self.tick_buffer: deque = deque(maxlen=config.tick_buffer_size)
        self.websocket_connected = False
        self.tick_handlers: List[Callable] = []
        self.latency_tracker = LatencyTracker()
        self._listener_task: Optional[asyncio.Task] = None
        self._processor_task: Optional[asyncio.Task] = None
        self._reconnection_task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """Start WebSocket connection and data processing."""
        logger.info("Starting data stream processor")
        
        try:
            # Connect WebSocket
            await self.broker.connect_websocket()
            self.websocket_connected = True
            logger.info("WebSocket connected successfully")
            
            # Start processing loops
            self._listener_task = asyncio.create_task(self._websocket_listener_loop())
            self._processor_task = asyncio.create_task(self._buffer_processor_loop())
            self._reconnection_task = asyncio.create_task(self._reconnection_monitor_loop())
            
            logger.info("✅ Data stream processor started")
            
        except Exception as e:
            logger.error(f"Failed to start data stream processor: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop WebSocket connection."""
        logger.info("Stopping data stream processor")
        
        # Cancel tasks
        for task in [self._listener_task, self._processor_task, self._reconnection_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.websocket_connected = False
        
        try:
            await self.broker.disconnect_websocket()
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")
        
        logger.info("Data stream processor stopped")
    
    async def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe to real-time ticks for an instrument."""
        instrument_key = f"{exchange}:{symbol}"
        
        if instrument_key not in self.subscribed_instruments:
            try:
                await self.broker.subscribe_ticks([instrument_key])
                self.subscribed_instruments.add(instrument_key)
                logger.info(f"✅ Subscribed to {instrument_key}")
            except Exception as e:
                logger.error(f"Failed to subscribe to {instrument_key}: {e}")
    
    async def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe from real-time ticks."""
        instrument_key = f"{exchange}:{symbol}"
        
        if instrument_key in self.subscribed_instruments:
            try:
                await self.broker.unsubscribe_ticks([instrument_key])
                self.subscribed_instruments.remove(instrument_key)
                logger.info(f"Unsubscribed from {instrument_key}")
            except Exception as e:
                logger.error(f"Failed to unsubscribe from {instrument_key}: {e}")
    
    def register_tick_handler(self, handler: Callable) -> None:
        """Register callback for tick updates."""
        self.tick_handlers.append(handler)
        logger.debug(f"Registered tick handler (total: {len(self.tick_handlers)})")
    
    async def _websocket_listener_loop(self) -> None:
        """Listen to WebSocket and buffer incoming ticks."""
        while self.websocket_connected:
            try:
                # Receive raw tick from WebSocket
                raw_tick = await self.broker.receive_websocket_message()
                
                # Add to buffer for processing
                self.tick_buffer.append(raw_tick)
                
                # Check buffer overflow
                if len(self.tick_buffer) >= self.config.tick_buffer_size * 0.95:
                    logger.warning(
                        f"Tick buffer at {len(self.tick_buffer)}/{self.config.tick_buffer_size}, "
                        "approaching overflow"
                    )
                
            except Exception as e:
                logger.error(f"WebSocket listener error: {e}")
                self.websocket_connected = False
                break
    
    async def _buffer_processor_loop(self) -> None:
        """Process buffered ticks with normalization."""
        while True:
            try:
                if len(self.tick_buffer) == 0:
                    await asyncio.sleep(0.001)  # 1ms sleep when buffer empty
                    continue
                
                # Get oldest tick from buffer
                raw_tick = self.tick_buffer.popleft()
                
                # Normalize to StandardTick (<10ms)
                start_time = time.time()
                standard_tick = self._normalize_tick(raw_tick)
                normalization_time = (time.time() - start_time) * 1000
                
                if normalization_time > self.config.max_tick_processing_latency_ms:
                    logger.warning(
                        f"Tick normalization took {normalization_time:.2f}ms "
                        f"(>{self.config.max_tick_processing_latency_ms}ms threshold)"
                    )
                
                # Calculate data latency
                if hasattr(standard_tick, 'timestamp') and standard_tick.timestamp:
                    latency_ms = (datetime.now() - standard_tick.timestamp).total_seconds() * 1000
                    self.latency_tracker.record(latency_ms)
                
                # Dispatch to handlers
                for handler in self.tick_handlers:
                    try:
                        await handler(standard_tick)
                    except Exception as e:
                        logger.error(f"Tick handler error: {e}")
                        
            except Exception as e:
                logger.error(f"Buffer processor error: {e}")
    
    async def _reconnection_monitor_loop(self) -> None:
        """Monitor WebSocket and automatically reconnect."""
        while True:
            try:
                await asyncio.sleep(5)
                
                if not self.websocket_connected:
                    logger.info("Attempting WebSocket reconnection...")
                    try:
                        await self.broker.connect_websocket()
                        
                        # Re-subscribe to all instruments
                        if self.subscribed_instruments:
                            await self.broker.subscribe_ticks(list(self.subscribed_instruments))
                            logger.info(f"Re-subscribed to {len(self.subscribed_instruments)} instruments")
                        
                        self.websocket_connected = True
                        logger.info("✅ WebSocket reconnected successfully")
                        
                        # Restart listener loop
                        self._listener_task = asyncio.create_task(self._websocket_listener_loop())
                        
                    except Exception as e:
                        logger.error(f"WebSocket reconnection failed: {e}")
                        
            except Exception as e:
                logger.error(f"Reconnection monitor error: {e}")
    
    def _normalize_tick(self, raw_tick: Dict) -> StandardTick:
        """Convert Dhan tick format to StandardTick."""
        # Implementation depends on Dhan API tick format
        # This is a placeholder implementation
        return StandardTick(
            symbol=raw_tick.get('symbol', ''),
            bid=raw_tick.get('bid', 0.0),
            ask=raw_tick.get('ask', 0.0),
            last=raw_tick.get('ltp', 0.0),
            volume=raw_tick.get('volume', 0.0),
            timestamp=raw_tick.get('timestamp', datetime.now()),
            broker="dhan"
        )
    
    def get_status(self) -> Dict:
        """Return data stream status."""
        return {
            "websocket_connected": self.websocket_connected,
            "subscribed_instruments": len(self.subscribed_instruments),
            "buffer_size": len(self.tick_buffer),
            "buffer_capacity": self.tick_buffer.maxlen,
            "latency_metrics": self.latency_tracker.get_metrics()
        }
    
    def is_healthy(self) -> bool:
        """Check if data stream is healthy."""
        return self.websocket_connected and len(self.tick_buffer) < self.config.tick_buffer_size * 0.95
