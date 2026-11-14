"""
╔══════════════════════════════════════════════════════════════╗
║              INDIAN MARKET ENGINE - COMPONENTS               ║
║          Core subsystem components for engine operation       ║
╚══════════════════════════════════════════════════════════════╝

This package contains all the core components that make up the Indian Market Engine:

- connection_manager: Handles Dhan API connectivity with resilience patterns
- session_manager: Tracks market session states and transitions
- instrument_registry: Fast lookup of instrument specifications
- data_stream_processor: Real-time tick data processing via WebSocket
- order_manager: Order validation, execution, and state management
- position_manager: Position tracking with real-time P&L calculation
- event_publisher: Internal pub-sub event system
- integration_bridge: Interface to all ZOHRA divisions
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
    'ConnectionManager',
    'SessionManager', 
    'InstrumentRegistry',
    'DataStreamProcessor',
    'OrderManager',
    'PositionManager',
    'EventPublisher',
    'IntegrationBridge'
]