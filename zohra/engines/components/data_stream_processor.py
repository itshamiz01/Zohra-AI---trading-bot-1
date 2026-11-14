"""
╔══════════════════════════════════════════════════════════════╗
║       INDIAN MARKET ENGINE - DATA STREAM PROCESSOR           ║
║     Real-time tick data processing via WebSocket stream       ║
╚══════════════════════════════════════════════════════════════╝

The Data Stream Processor handles:
- WebSocket connection management for real-time data
- Tick data normalization to StandardTick format (<10ms)
- Buffer management to prevent data loss (10,000 message capacity)
- Subscription management for instruments
- Latency tracking and monitoring
- Automatic reconnection with re-subscription
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Set, Callable, List, Dict, Any, Optional

from ...brokers.interfaces import UnifiedBrokerAdapter
from ...brokers.models import StandardTick
from ..config import EngineConfig
from ..models import LatencyMetrics

logger = logging.getLogger(__name__)


class LatencyTracker:
    """Tracks latency metrics with percentile calculation."""
    
    def __init__(self, max_samples: int = 10000):
        self.samples: deque = deque(maxlen=max_samples)
        self.operation_name = ""
    
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
        index = min(int(len(sorted_samples) * percentile / 100), len(sorted_samples) - 1)
        return sorted_samples[index]
    
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
    """
    Processes real-time market data from WebSocket stream.
    
    Manages WebSocket connectivity for real-time tick data, normalizes
    incoming data to StandardTick format, and distributes to registered handlers.
    """
    
    def __init__(self, broker: UnifiedBrokerAdapter, config: EngineConfig):
        self.broker = broker
        self.config = config
        
        # Subscription management
        self.subscribed_instruments: Set[str] = set()
        self.tick_handlers: List[Callable[[StandardTick], None]] = []
        
        # Data processing
        self.tick_buffer: deque = deque(maxlen=config.tick_buffer_size)
        self.websocket_connected = False
        self.is_processing = False
        
        # Monitoring
        self.latency_tracker = LatencyTracker()
        self.total_ticks_processed = 0
        self.buffer_overflows = 0
        self.processing_errors = 0
        
        # Tasks
        self._websocket_task: Optional[asyncio.Task] = None
        self._processor_task: Optional[asyncio.Task] = None
        self._reconnection_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start WebSocket connection and data processing."""
        logger.info("🚀 Starting data stream processor")
        
        try:
            # Connect WebSocket (placeholder - actual implementation depends on Dhan WebSocket API)
            await self._connect_websocket()
            
            # Start processing loops
            self._websocket_task = asyncio.create_task(self._websocket_listener_loop())
            self._processor_task = asyncio.create_task(self._buffer_processor_loop())
            self._reconnection_task = asyncio.create_task(self._reconnection_monitor_loop())
            
            self.is_processing = True
            logger.info("✅ Data stream processor started")
            
        except Exception as e:
            logger.error(f"❌ Failed to start data stream processor: {e}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop WebSocket connection and processing."""
        logger.info("🛑 Stopping data stream processor")
        self.is_processing = False
        
        # Cancel all tasks
        tasks = [self._websocket_task, self._processor_task, self._reconnection_task]
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Disconnect WebSocket
        await self._disconnect_websocket()
        
        logger.info("✅ Data stream processor stopped")
    
    async def _connect_websocket(self) -> None:
        """Connect to WebSocket stream."""
        # This is a placeholder implementation
        # In a real implementation, this would establish WebSocket connection to Dhan feed
        try:
            logger.info("Connecting to Dhan WebSocket feed...")
            
            # Simulate connection delay
            await asyncio.sleep(1)
            
            self.websocket_connected = True
            logger.info("✅ WebSocket connected")
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            raise
    
    async def _disconnect_websocket(self) -> None:
        """Disconnect from WebSocket stream."""
        if self.websocket_connected:
            self.websocket_connected = False
            logger.info("WebSocket disconnected")
    
    async def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe to real-time ticks for an instrument."""
        instrument_key = f"{exchange}:{symbol}"
        
        if instrument_key not in self.subscribed_instruments:
            # In real implementation, this would send subscription message to WebSocket
            logger.debug(f"Subscribing to {instrument_key}")
            
            # Simulate subscription
            await self._send_subscription_message(instrument_key, action="SUBSCRIBE")
            
            self.subscribed_instruments.add(instrument_key)
            logger.info(f"📊 Subscribed to {instrument_key}")
    
    async def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe from real-time ticks."""
        instrument_key = f"{exchange}:{symbol}"
        
        if instrument_key in self.subscribed_instruments:
            # Send unsubscription message
            await self._send_subscription_message(instrument_key, action="UNSUBSCRIBE")
            
            self.subscribed_instruments.remove(instrument_key)
            logger.info(f"📊 Unsubscribed from {instrument_key}")
    
    async def _send_subscription_message(self, instrument_key: str, action: str) -> None:
        """Send subscription/unsubscription message to WebSocket."""
        # This is a placeholder - actual implementation would send WebSocket message
        logger.debug(f"WebSocket {action}: {instrument_key}")
    
    def register_tick_handler(self, handler: Callable[[StandardTick], Any]) -> None:
        """Register callback for tick updates."""
        self.tick_handlers.append(handler)
        logger.debug(f"Registered tick handler: {handler.__name__}")
    
    def unregister_tick_handler(self, handler: Callable[[StandardTick], Any]) -> None:
        """Unregister tick handler."""
        if handler in self.tick_handlers:
            self.tick_handlers.remove(handler)
            logger.debug(f"Unregistered tick handler: {handler.__name__}")
    
    async def _websocket_listener_loop(self) -> None:
        """Listen to WebSocket and buffer incoming ticks."""
        while self.websocket_connected and self.is_processing:
            try:
                # Simulate receiving WebSocket messages
                # In real implementation, this would await WebSocket messages
                await self._receive_and_buffer_tick()
                
                # Small delay to prevent tight loop in simulation
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                logger.info("WebSocket listener loop cancelled")
                break
            except Exception as e:
                logger.error(f"WebSocket listener error: {e}")
                self.websocket_connected = False
                break
    
    async def _receive_and_buffer_tick(self) -> None:
        """Simulate receiving and buffering a tick."""
        # This is simulation - real implementation would receive from WebSocket
        if self.subscribed_instruments:
            # Generate sample tick for first subscribed instrument
            instrument_key = next(iter(self.subscribed_instruments))
            symbol = instrument_key.split(':')[1]
            
            raw_tick = {
                "symbol": symbol,
                "exchange": "NSE",
                "ltp": 100.0 + (time.time() % 10),  # Simulated price
                "bid": 99.95,
                "ask": 100.05,
                "volume": 1000,
                "timestamp": datetime.now(),
                "asset_class": "EQUITY"
            }
            
            # Add to buffer for processing
            if len(self.tick_buffer) >= self.config.tick_buffer_size * 0.95:
                logger.warning(f"Tick buffer at {len(self.tick_buffer)}/{self.config.tick_buffer_size}, approaching overflow")
                
                if len(self.tick_buffer) >= self.config.tick_buffer_size:
                    # Buffer full - drop oldest tick
                    self.tick_buffer.popleft()
                    self.buffer_overflows += 1
                    logger.warning("Buffer overflow - dropped oldest tick")
            
            self.tick_buffer.append(raw_tick)
    
    async def _buffer_processor_loop(self) -> None:
        """Process buffered ticks with normalization."""
        while self.is_processing:
            try:
                if len(self.tick_buffer) == 0:
                    await asyncio.sleep(0.001)  # 1ms sleep when buffer empty
                    continue
                
                # Get oldest tick from buffer
                raw_tick = self.tick_buffer.popleft()
                
                # Normalize to StandardTick with latency tracking
                start_time = time.time()
                standard_tick = self._normalize_tick(raw_tick)
                normalization_time = (time.time() - start_time) * 1000
                
                # Track normalization latency
                self.latency_tracker.record(normalization_time)
                
                if normalization_time > self.config.max_tick_processing_latency_ms:
                    logger.warning(f"Tick normalization took {normalization_time:.2f}ms (>{self.config.max_tick_processing_latency_ms}ms threshold)")
                
                # Calculate data latency if exchange timestamp available
                if hasattr(standard_tick, 'data_latency_ms'):
                    exchange_timestamp = raw_tick.get('timestamp')
                    if exchange_timestamp:
                        data_latency = (datetime.now() - exchange_timestamp).total_seconds() * 1000
                        standard_tick.data_latency_ms = data_latency
                
                # Dispatch to handlers
                await self._dispatch_tick(standard_tick)
                self.total_ticks_processed += 1
                
            except asyncio.CancelledError:
                logger.info("Buffer processor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Buffer processor error: {e}")
                self.processing_errors += 1
    
    def _normalize_tick(self, raw_tick: Dict) -> StandardTick:
        """
        Convert raw tick format to StandardTick.
        
        This method normalizes Dhan-specific tick format to the standard
        MAL tick format used throughout the system.
        """
        try:
            return StandardTick(
                symbol=raw_tick['symbol'],
                bid=float(raw_tick.get('bid', raw_tick.get('ltp', 0))),
                ask=float(raw_tick.get('ask', raw_tick.get('ltp', 0))),
                last=float(raw_tick.get('ltp', 0)),
                volume=float(raw_tick.get('volume', 0)),
                timestamp=raw_tick.get('timestamp', datetime.now()),
                broker="dhan"
            )
        except Exception as e:
            logger.error(f"Error normalizing tick {raw_tick}: {e}")
            # Return a default tick to prevent crashes
            return StandardTick(
                symbol=raw_tick.get('symbol', 'UNKNOWN'),
                bid=0.0,
                ask=0.0,
                last=0.0,
                volume=0.0,
                timestamp=datetime.now(),
                broker="dhan"
            )
    
    async def _dispatch_tick(self, tick: StandardTick) -> None:
        """Dispatch tick to all registered handlers."""
        for handler in self.tick_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(tick)
                else:
                    handler(tick)
            except Exception as e:
                logger.error(f"Tick handler error ({handler.__name__}): {e}")
    
    async def _reconnection_monitor_loop(self) -> None:
        """Monitor WebSocket and automatically reconnect."""
        while self.is_processing:
            try:
                await asyncio.sleep(self.config.websocket_reconnect_delay_sec)
                
                if not self.websocket_connected:
                    logger.info("🔄 Attempting WebSocket reconnection...")
                    
                    try:
                        await self._connect_websocket()
                        
                        # Re-subscribe to all instruments
                        if self.subscribed_instruments:
                            logger.info(f"Re-subscribing to {len(self.subscribed_instruments)} instruments")
                            
                            for instrument_key in list(self.subscribed_instruments):
                                await self._send_subscription_message(instrument_key, "SUBSCRIBE")
                        
                        logger.info("✅ WebSocket reconnected successfully")
                        
                        # Restart listener loop
                        if self._websocket_task:
                            self._websocket_task.cancel()
                        self._websocket_task = asyncio.create_task(self._websocket_listener_loop())
                        
                    except Exception as e:
                        logger.error(f"WebSocket reconnection failed: {e}")
                
            except asyncio.CancelledError:
                logger.info("Reconnection monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Reconnection monitor error: {e}")
    
    def get_status(self) -> Dict:
        """Return data stream processor status."""
        return {
            "websocket_connected": self.websocket_connected,
            "is_processing": self.is_processing,
            "subscribed_instruments": len(self.subscribed_instruments),
            "buffer_size": len(self.tick_buffer),
            "buffer_capacity": self.tick_buffer.maxlen,
            "total_ticks_processed": self.total_ticks_processed,
            "buffer_overflows": self.buffer_overflows,
            "processing_errors": self.processing_errors,
            "latency_metrics": self.latency_tracker.get_metrics(),
            "registered_handlers": len(self.tick_handlers)
        }
    
    def is_healthy(self) -> bool:
        """Check if data stream processor is healthy."""
        return (
            self.websocket_connected and 
            self.is_processing and 
            self.processing_errors < 100  # Allow some errors but not too many
        )
    
    def get_subscribed_instruments(self) -> List[str]:
        """Get list of currently subscribed instruments."""
        return list(self.subscribed_instruments)
    
    async def resubscribe_all(self) -> None:
        """Resubscribe to all currently subscribed instruments."""
        instruments = list(self.subscribed_instruments)
        self.subscribed_instruments.clear()
        
        for instrument_key in instruments:
            exchange, symbol = instrument_key.split(':', 1)
            await self.subscribe(symbol, exchange)