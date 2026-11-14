"""
╔══════════════════════════════════════════════════════════════╗
║         INDIAN MARKET ENGINE - CORE COMPONENTS               ║
║  Modular subsystems for NSE/BSE market operations            ║
╚══════════════════════════════════════════════════════════════╝

This package contains the 9 core components of the Indian Market Engine:

1. ConnectionManager: Dhan API connectivity with resilience patterns
2. SessionManager: Market session state tracking and enforcement
3. InstrumentRegistry: Fast instrument specification lookup and caching
4. DataStreamProcessor: Real-time WebSocket tick processing
5. OrderManager: Order validation, submission, and state machine
6. PositionManager: Position tracking with real-time P&L calculation
7. EventPublisher: Internal pub-sub event communication
8. IntegrationBridge: ZOHRA divisions integration layer
9. Engine Coordinator: Main orchestrator (in parent module)

Each component is designed for:
- High performance (sub-100ms latency targets)
- Operational resilience (retries, circuit breakers)
- Complete audit trail (structured logging)
- Clean separation of concerns
"""

from .connection_manager import ConnectionManager
from .session_manager import SessionManager
from .instrument_registry import InstrumentRegistry
from .data_stream_processor import DataStreamProcessor
from .order_manager import OrderManager
from .position_manager import PositionManager
from .event_publisher import EventPublisher
from .integration_bridge import IntegrationBridge

__all__ = [
    "ConnectionManager",
    "SessionManager",
    "InstrumentRegistry",
    "DataStreamProcessor",
    "OrderManager",
    "PositionManager",
    "EventPublisher",
    "IntegrationBridge",
]
