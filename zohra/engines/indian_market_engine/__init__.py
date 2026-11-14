"""
╔══════════════════════════════════════════════════════════════╗
║                 INDIAN MARKET ENGINE - PACKAGE               ║
║   NSE/BSE Trading Engine with AI Integration & Risk Mgmt     ║
╚══════════════════════════════════════════════════════════════╝

The Indian Market Engine provides comprehensive access to NSE and BSE markets
through the Dhan adapter within the ZOHRA AI OS architecture.

Key Features:
- Multi-asset trading (Equity, Futures, Options)
- Real-time streaming data processing
- AI-driven decision making with veto authority
- Risk management integration
- Portfolio tracking and P&L calculation
- Integration with all ZOHRA divisions

Usage:
    from zohra.engines.indian_market_engine import IndianMarketEngine
    from zohra.engines.indian_market_engine.config import EngineConfig
    
    config = EngineConfig()
    engine = IndianMarketEngine(config, broker_manager, integration_bridge)
    await engine.start()
"""

from .config import EngineConfig
from .engine import IndianMarketEngine
from .models import (
    TradeSetup,
    AIEvaluation,
    AIDecision,
    MarketSession,
    SessionTransition,
    CapitalAllocation,
    PerformanceMetrics,
    HealthStatus,
    CircuitState
)
from .logging_config import setup_logging, LogEntry
from .components import (
    ConnectionManager,
    SessionManager,
    InstrumentRegistry,
    DataStreamProcessor,
    OrderManager,
    PositionManager,
    EventPublisher,
    IntegrationBridge
)

__all__ = [
    # Core Engine
    "IndianMarketEngine",
    
    # Configuration
    "EngineConfig",
    
    # Data Models
    "TradeSetup",
    "AIEvaluation",
    "AIDecision",
    "MarketSession",
    "SessionTransition",
    "CapitalAllocation",
    "PerformanceMetrics",
    "HealthStatus",
    "CircuitState",
    
    # Logging
    "setup_logging",
    "LogEntry",
    
    # Core Components
    "ConnectionManager",
    "SessionManager",
    "InstrumentRegistry",
    "DataStreamProcessor",
    "OrderManager",
    "PositionManager",
    "EventPublisher",
    "IntegrationBridge",
]

__version__ = "1.0.0"
__author__ = "ZOHRA AI OS"
__description__ = "Indian Market Engine for NSE/BSE trading operations"
