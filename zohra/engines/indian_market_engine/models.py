"""
Indian Market Engine specific data models extending MAL standards.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Any, Optional


class MarketSession(str, Enum):
    """Market session states for Indian exchanges."""
    PRE_OPEN = "PRE_OPEN"
    REGULAR = "REGULAR"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class AIDecision(str, Enum):
    """AI decision outcomes for trade setups."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    DEFER = "DEFER"


@dataclass
class TradeSetup:
    """Complete trade setup for AI evaluation."""
    symbol: str
    exchange: str
    asset_class: str
    side: str  # "BUY" or "SELL"
    suggested_quantity: int
    suggested_entry: Decimal
    suggested_stop_loss: Decimal
    suggested_take_profit: Decimal
    technical_indicators: Dict[str, Any]
    market_context: Dict[str, Any]
    confidence_score: float
    setup_id: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AIEvaluation:
    """AI decision engine evaluation result."""
    setup_id: str
    decision: AIDecision
    decision_score: float
    reasoning: str
    timestamp: datetime
    evaluation_time_ms: float


@dataclass
class SessionTransition:
    """Market session state change event."""
    previous_session: MarketSession
    current_session: MarketSession
    transition_time: datetime
    next_transition_time: Optional[datetime] = None


@dataclass
class CapitalAllocation:
    """Capital allocation from Capital Allocator."""
    allocated_capital: Decimal
    utilized_capital: Decimal
    available_capital: Decimal
    allocation_time: datetime
    performance_score: float


@dataclass
class PerformanceMetrics:
    """Performance metrics for Analytics Engine."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: Decimal
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: Decimal
    avg_execution_latency_ms: float
    avg_data_latency_ms: float


class HealthStatus(str, Enum):
    """Engine health status."""
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Blocking calls
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class HealthStatus(str, Enum):
    """Engine health status."""
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
