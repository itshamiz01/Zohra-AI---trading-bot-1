# Indian Market Engine

Enterprise-grade trading engine for NSE (National Stock Exchange) and BSE (Bombay Stock Exchange) markets within the ZOHRA AI OS Trading Division.

## 🏗️ Architecture Overview

The Indian Market Engine consists of 9 core components:

### Core Components

1. **Engine Coordinator** (`indian_market_engine.py`)
   - Main orchestrator and public API
   - Component lifecycle management
   - Health monitoring and graceful shutdown

2. **Connection Manager** (`components/connection_manager.py`)
   - Dhan API connectivity with resilience patterns
   - Exponential backoff retry logic
   - Circuit breaker pattern
   - Health monitoring with heartbeat

3. **Session Manager** (`components/session_manager.py`)
   - Market session state tracking (PRE_OPEN, REGULAR, CLOSING, CLOSED)
   - Session transition detection and broadcasting
   - Session-specific trading rule enforcement

4. **Instrument Registry** (`components/instrument_registry.py`)
   - Fast instrument specification lookup (<10ms)
   - Daily cache refresh at 08:00 IST
   - Support for Equity, Futures, and Options

5. **Data Stream Processor** (`components/data_stream_processor.py`)
   - WebSocket real-time tick processing
   - Tick normalization to StandardTick format (<10ms)
   - Buffering with 10,000 message capacity
   - Data latency tracking

6. **Order Manager** (`components/order_manager.py`)
   - Order validation against instrument specifications
   - Support for MARKET, LIMIT, STOP_LOSS, STOP_LIMIT orders
   - Order state machine tracking
   - Execution latency tracking

7. **Position Manager** (`components/position_manager.py`)
   - Real-time position tracking
   - Floating P&L calculation on tick updates
   - Stop loss/take profit trigger detection
   - Position queries with filtering

8. **Event Publisher** (`components/event_publisher.py`)
   - Internal pub-sub event communication
   - Event queuing and replay capability

9. **Integration Bridge** (`components/integration_bridge.py`)
   - AI Decision Engine integration
   - Risk Engine integration
   - Portfolio Manager integration
   - Capital Allocator integration
   - Analytics, Learning, Memory, Research, Voice, Dashboard integration

## 📋 Features

- **Multi-Asset Support**: Trade Equity, Futures, and Options simultaneously
- **Low-Latency Operation**: Sub-100ms order execution, sub-10ms tick processing
- **AI Integration**: Autonomous decision-making with veto authority
- **Risk Management**: Comprehensive risk validation before execution
- **Operational Resilience**: Circuit breakers, retries, automatic reconnection
- **Audit Compliance**: Complete structured logging in JSONL format
- **Performance Tracking**: Real-time metrics for latency, P&L, and execution quality

## ⚙️ Configuration

Configuration is managed through environment variables using Pydantic models.

### Environment Variables

Create a `.env` file with the following variables (prefix: `INDIAN_ENGINE_`):

```env
# Dhan API Credentials
INDIAN_ENGINE_DHAN_CLIENT_ID=your_client_id
INDIAN_ENGINE_DHAN_ACCESS_TOKEN=your_access_token

# Connection Settings
INDIAN_ENGINE_MAX_CONNECTION_RETRIES=5
INDIAN_ENGINE_HEARTBEAT_INTERVAL_SEC=30

# Circuit Breaker Settings
INDIAN_ENGINE_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
INDIAN_ENGINE_CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SEC=30

# Data Stream Settings
INDIAN_ENGINE_TICK_BUFFER_SIZE=10000
INDIAN_ENGINE_MAX_TICK_PROCESSING_LATENCY_MS=10.0

# Intraday Settings
INDIAN_ENGINE_INTRADAY_MODE=true
INDIAN_ENGINE_AUTO_CLOSE_POSITIONS_AT_SESSION_END=true

# Risk Limits
INDIAN_ENGINE_MAX_POSITION_SIZE=1000
INDIAN_ENGINE_MAX_PORTFOLIO_EXPOSURE=100000.0

# Log Settings
INDIAN_ENGINE_LOG_FILE=logs/indian_engine.log
INDIAN_ENGINE_LOG_LEVEL=INFO
INDIAN_ENGINE_LOG_RETENTION_DAYS=90

# Integration URLs
INDIAN_ENGINE_AI_ENGINE_URL=http://localhost:8001
INDIAN_ENGINE_RISK_ENGINE_URL=http://localhost:8002
INDIAN_ENGINE_PORTFOLIO_URL=http://localhost:8003
INDIAN_ENGINE_CAPITAL_URL=http://localhost:8004

# Simulation Mode
INDIAN_ENGINE_SIMULATION_MODE=false
```

## 🚀 Usage

### Basic Initialization

```python
import asyncio
from zohra.engines.indian_market_engine import IndianMarketEngine
from zohra.engines.indian_market_engine.config import EngineConfig
from zohra.engines.indian_market_engine.components import IntegrationBridge
from zohra.brokers.manager import broker_manager

async def main():
    # Load configuration
    config = EngineConfig()
    
    # Initialize integration bridge
    integration_bridge = IntegrationBridge(config)
    
    # Create engine instance
    engine = IndianMarketEngine(
        config=config,
        broker_manager=broker_manager,
        integration_bridge=integration_bridge
    )
    
    # Start engine
    await engine.start()
    
    # Submit trade setup
    from zohra.engines.indian_market_engine.models import TradeSetup
    from decimal import Decimal
    from datetime import datetime
    
    setup = TradeSetup(
        symbol="RELIANCE",
        exchange="NSE",
        asset_class="EQUITY",
        side="BUY",
        suggested_quantity=1,
        suggested_entry=Decimal("2450.00"),
        suggested_stop_loss=Decimal("2420.00"),
        suggested_take_profit=Decimal("2500.00"),
        technical_indicators={},
        market_context={},
        confidence_score=0.85,
        setup_id="SETUP001",
        timestamp=datetime.now()
    )
    
    execution = await engine.submit_trade_setup(setup)
    print(f"Execution result: {execution}")
    
    # Query positions
    positions = await engine.get_positions(symbol="RELIANCE")
    print(f"Open positions: {positions}")
    
    # Get health status
    health = engine.get_health_status()
    print(f"Engine health: {health}")
    
    # Graceful shutdown
    await engine.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## 📊 Health Monitoring

The engine provides comprehensive health monitoring:

```python
health = engine.get_health_status()
# Returns:
# {
#     "engine_status": "RUNNING",
#     "health_status": "HEALTHY",
#     "startup_time": "2025-06-05T09:00:00",
#     "uptime_seconds": 3600,
#     "connection_status": "CONNECTED",
#     "data_stream_status": {...},
#     "session": "REGULAR",
#     "instruments_loaded": 5000,
#     "active_positions": 5,
#     "pending_orders": 2
# }
```

## 📝 Logging

All operations are logged in structured JSONL format for audit compliance:

```jsonl
{"timestamp": "2025-06-05T09:15:23.456Z", "level": "INFO", "category": "order", "event": "submitted", "ticket": "ORD123456", "symbol": "RELIANCE", "side": "BUY"}
{"timestamp": "2025-06-05T10:23:45.678Z", "level": "INFO", "category": "position", "event": "opened", "ticket": "POS789012", "symbol": "NIFTY25JUN24000CE"}
```

Logs are automatically rotated daily and compressed after 7 days.

## 🧪 Testing

Run tests using pytest:

```bash
# Run all tests
pytest zohra/engines/indian_market_engine/tests/

# Run specific test category
pytest zohra/engines/indian_market_engine/tests/test_connection_manager.py

# Run with coverage
pytest --cov=zohra.engines.indian_market_engine
```

## 📚 Requirements

### Requirements Validated

This implementation validates the following requirements from `requirements.md`:

- **Requirement 21.1**: Configuration management with environment variables
- **Requirement 21.2**: Pydantic configuration models  
- **Requirement 19.1**: Structured logging in JSONL format
- **Requirement 19.8**: Log operations with complete context

### Component Coverage

- ✅ Engine Coordinator
- ✅ Connection Manager (with retry & circuit breaker)
- ✅ Session Manager (market hours tracking)
- ✅ Instrument Registry (fast lookup & caching)
- ✅ Data Stream Processor (WebSocket handling)
- ✅ Order Manager (validation & state machine)
- ✅ Position Manager (real-time P&L)
- ✅ Event Publisher (pub-sub system)
- ✅ Integration Bridge (ZOHRA divisions)

## 🔒 Security

- API credentials stored in environment variables
- Sensitive configuration encrypted with Pydantic SecretStr
- Comprehensive audit trail for regulatory compliance
- Circuit breaker protection against cascading failures

## 📖 Documentation

- [Design Document](../../../../.kiro/specs/indian-market-engine/design.md)
- [Requirements Document](../../../../.kiro/specs/indian-market-engine/requirements.md)
- [Tasks Breakdown](../../../../.kiro/specs/indian-market-engine/tasks.md)
- [MAL Architecture](../../../docs/MAL_ARCHITECTURE.md)

## 🤝 Contributing

This engine follows the ZOHRA AI OS architecture standards. All contributions must:

1. Pass property-based tests
2. Maintain audit trail compliance
3. Follow MAL standardization
4. Include comprehensive logging

## 📄 License

Part of the ZOHRA AI OS Trading Division - Proprietary

---

**Version**: 1.0.0  
**Status**: Task 1 Complete ✅  
**Last Updated**: 2025-06-05
