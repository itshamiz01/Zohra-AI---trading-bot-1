"""
╔══════════════════════════════════════════════════════════════╗
║         INDIAN MARKET ENGINE - DATA MODELS                   ║
║        Specialized data structures for engine operations      ║
╚══════════════════════════════════════════════════════════════╝

Data models specific to the Indian Market Engine that extend the standard
MAL models. These models handle Indian market-specific requirements and
provide additional functionality for AI integration and trading operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Any, Optional, List


# ═══ Enumerations ═══

class MarketSession(Enum):
    """Market session states for NSE/BSE."""
    PRE_OPEN = "PRE_OPEN"
    REGULAR = "REGULAR"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class AIDecision(Enum):
    """AI decision outcomes for trade evaluation."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    DEFER = "DEFER"


class AssetClass(Enum):
    """Asset classes supported in Indian markets."""
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class OrderSide(Enum):
    """Order side/direction."""
    BUY = "BUY"
    SELL = "SELL"


class HealthStatus(Enum):
    """Engine health status levels."""
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


# ═══ Core Data Models ═══

@dataclass
class TradeSetup:
    """
    Complete trade setup for AI evaluation and execution.
    
    Contains all information needed for the AI to evaluate a trading opportunity
    and for the engine to execute the trade if approved.
    """
    setup_id: str
    symbol: str
    exchange: str
    asset_class: AssetClass
    side: OrderSide
    suggested_quantity: int
    suggested_entry: Decimal
    suggested_stop_loss: Decimal
    suggested_take_profit: Decimal
    technical_indicators: Dict[str, Any]
    market_context: Dict[str, Any]
    confidence_score: float  # 0.0 to 1.0
    timestamp: datetime
    strategy_name: Optional[str] = None
    timeframe: Optional[str] = None
    risk_reward_ratio: Optional[float] = None
    
    def __post_init__(self):
        """Validate setup data after initialization."""
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            raise ValueError("Confidence score must be between 0.0 and 1.0")
        
        if self.suggested_quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        if self.suggested_entry <= 0:
            raise ValueError("Entry price must be positive")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "setup_id": self.setup_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_class": self.asset_class.value,
            "side": self.side.value,
            "suggested_quantity": self.suggested_quantity,
            "suggested_entry": float(self.suggested_entry),
            "suggested_stop_loss": float(self.suggested_stop_loss),
            "suggested_take_profit": float(self.suggested_take_profit),
            "technical_indicators": self.technical_indicators,
            "market_context": self.market_context,
            "confidence_score": self.confidence_score,
            "timestamp": self.timestamp.isoformat(),
            "strategy_name": self.strategy_name,
            "timeframe": self.timeframe,
            "risk_reward_ratio": self.risk_reward_ratio
        }


@dataclass
class AIEvaluation:
    """
    AI decision engine evaluation result.
    
    Contains the AI's decision on a trade setup along with reasoning
    and confidence metrics.
    """
    setup_id: str
    decision: AIDecision
    decision_score: float  # 0.0 to 1.0
    reasoning: str
    timestamp: datetime
    evaluation_time_ms: float
    confidence_factors: Dict[str, float] = field(default_factory=dict)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "setup_id": self.setup_id,
            "decision": self.decision.value,
            "decision_score": self.decision_score,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
            "evaluation_time_ms": self.evaluation_time_ms,
            "confidence_factors": self.confidence_factors,
            "risk_assessment": self.risk_assessment
        }


@dataclass
class SessionTransition:
    """
    Market session state change event.
    
    Represents a transition between market sessions with timing information.
    """
    previous_session: MarketSession
    current_session: MarketSession
    transition_time: datetime
    next_transition_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "previous_session": self.previous_session.value,
            "current_session": self.current_session.value,
            "transition_time": self.transition_time.isoformat(),
            "next_transition_time": self.next_transition_time.isoformat() if self.next_transition_time else None
        }


@dataclass
class CapitalAllocation:
    """
    Capital allocation from Capital Allocator.
    
    Tracks allocated, utilized, and available capital for the engine.
    """
    allocated_capital: Decimal
    utilized_capital: Decimal
    available_capital: Decimal
    allocation_time: datetime
    performance_score: float
    allocation_id: str = field(default_factory=lambda: f"CAP_{int(datetime.now().timestamp())}")
    
    @property
    def utilization_percentage(self) -> float:
        """Calculate capital utilization percentage."""
        if self.allocated_capital <= 0:
            return 0.0
        return float((self.utilized_capital / self.allocated_capital) * 100)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "allocation_id": self.allocation_id,
            "allocated_capital": float(self.allocated_capital),
            "utilized_capital": float(self.utilized_capital),
            "available_capital": float(self.available_capital),
            "allocation_time": self.allocation_time.isoformat(),
            "performance_score": self.performance_score,
            "utilization_percentage": self.utilization_percentage
        }


@dataclass
class PerformanceMetrics:
    """
    Performance metrics for Analytics Engine.
    
    Comprehensive performance statistics for the engine's trading activity.
    """
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal("0")
    total_profit: Decimal = Decimal("0")
    total_loss: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    avg_execution_latency_ms: float = 0.0
    avg_data_latency_ms: float = 0.0
    calculation_time: datetime = field(default_factory=datetime.now)
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    @property
    def profit_factor(self) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        if self.total_loss == 0:
            return float('inf') if self.total_profit > 0 else 0.0
        return float(self.total_profit / abs(self.total_loss))
    
    @property
    def sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio (simplified)."""
        # This is a simplified calculation - real Sharpe ratio needs more data
        if self.total_trades < 2:
            return 0.0
        avg_return = float(self.total_pnl) / self.total_trades
        return avg_return / max(float(abs(self.total_pnl)) / self.total_trades, 1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_pnl": float(self.total_pnl),
            "total_profit": float(self.total_profit),
            "total_loss": float(self.total_loss),
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": float(self.max_drawdown),
            "avg_execution_latency_ms": self.avg_execution_latency_ms,
            "avg_data_latency_ms": self.avg_data_latency_ms,
            "calculation_time": self.calculation_time.isoformat()
        }


@dataclass
class InstrumentSpec:
    """
    Extended instrument specification for Indian markets.
    
    Extends the standard MAL instrument model with Indian market-specific fields.
    """
    symbol: str
    exchange: str
    asset_class: AssetClass
    lot_size: int
    tick_size: Decimal
    contract_size: Decimal
    margin_required: Decimal
    expiry_date: Optional[datetime] = None
    sector: Optional[str] = None
    isin: Optional[str] = None
    trading_symbol: Optional[str] = None  # Dhan trading symbol
    segment: Optional[str] = None  # NSE_EQ, BSE_EQ, NSE_FNO, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_class": self.asset_class.value,
            "lot_size": self.lot_size,
            "tick_size": float(self.tick_size),
            "contract_size": float(self.contract_size),
            "margin_required": float(self.margin_required),
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "sector": self.sector,
            "isin": self.isin,
            "trading_symbol": self.trading_symbol,
            "segment": self.segment
        }


@dataclass
class LatencyMetrics:
    """
    Latency tracking for performance monitoring.
    
    Tracks various latency measurements across the engine's operations.
    """
    operation_name: str
    latency_ms: float
    timestamp: datetime
    success: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_name": self.operation_name,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error_message": self.error_message
        }


@dataclass
class SystemEvent:
    """
    System event for internal communication.
    
    Used for pub-sub communication between engine components.
    """
    event_type: str
    event_data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    source_component: Optional[str] = None
    event_id: str = field(default_factory=lambda: f"EVT_{int(datetime.now().timestamp() * 1000)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_data": self.event_data,
            "timestamp": self.timestamp.isoformat(),
            "source_component": self.source_component
        }


# ═══ Helper Functions ═══

def create_trade_setup(
    symbol: str,
    side: str,
    quantity: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    confidence: float,
    strategy_name: str = "default"
) -> TradeSetup:
    """Create a TradeSetup from basic parameters."""
    return TradeSetup(
        setup_id=f"SETUP_{int(datetime.now().timestamp() * 1000)}",
        symbol=symbol,
        exchange="NSE",  # Default to NSE
        asset_class=AssetClass.EQUITY,  # Default to equity
        side=OrderSide(side.upper()),
        suggested_quantity=quantity,
        suggested_entry=Decimal(str(entry_price)),
        suggested_stop_loss=Decimal(str(stop_loss)),
        suggested_take_profit=Decimal(str(take_profit)),
        technical_indicators={},
        market_context={},
        confidence_score=confidence,
        timestamp=datetime.now(),
        strategy_name=strategy_name
    )


def calculate_risk_reward_ratio(entry: Decimal, stop_loss: Decimal, take_profit: Decimal, side: OrderSide) -> float:
    """Calculate risk-reward ratio for a trade setup."""
    if side == OrderSide.BUY:
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
    else:  # SELL
        risk = abs(stop_loss - entry)
        reward = abs(entry - take_profit)
    
    if risk == 0:
        return 0.0
    
    return float(reward / risk)