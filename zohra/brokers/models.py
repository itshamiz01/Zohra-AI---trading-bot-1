"""
╔══════════════════════════════════════════════════════════════╗
║       MARKET ABSTRACTION LAYER — STANDARDIZED DATA MODELS   ║
║   Broker-agnostic data exchange types for the Trading Core   ║
╚══════════════════════════════════════════════════════════════╝

Every broker adapter MUST normalize its responses into these models.
The Trading Core never sees broker-specific data structures.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ════════════════════════════════════════════════════════════════
#  Enumerations
# ════════════════════════════════════════════════════════════════

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"


class InstrumentType(str, Enum):
    FOREX = "FOREX"
    EQUITY = "EQUITY"
    CRYPTO = "CRYPTO"
    COMMODITY = "COMMODITY"
    INDEX = "INDEX"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class MarketStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PRE_MARKET = "PRE_MARKET"
    POST_MARKET = "POST_MARKET"
    HALTED = "HALTED"


# ════════════════════════════════════════════════════════════════
#  Utility
# ════════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_id() -> str:
    return uuid.uuid4().hex[:16].upper()


# ════════════════════════════════════════════════════════════════
#  Standard Tick
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardTick:
    """Normalized real-time price tick."""
    symbol: str
    bid: float
    ask: float
    spread: float = 0.0
    mid: float = 0.0
    last: float = 0.0
    volume: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)
    broker: str = ""

    def __post_init__(self):
        if self.spread == 0.0:
            self.spread = self.ask - self.bid
        if self.mid == 0.0:
            self.mid = (self.bid + self.ask) / 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "spread": self.spread,
            "mid": self.mid,
            "last": self.last,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "broker": self.broker,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Candle (OHLCV)
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardCandle:
    """Normalized OHLCV bar."""
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    tick_volume: float = 0.0
    real_volume: float = 0.0
    broker: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_volume": self.tick_volume,
            "real_volume": self.real_volume,
            "broker": self.broker,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Balance / Account
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardBalance:
    """Normalized account balance snapshot."""
    balance: float
    equity: float
    margin: float = 0.0
    free_margin: float = 0.0
    profit: float = 0.0
    currency: str = "USD"
    leverage: int = 1
    login: str = ""
    server: str = ""
    broker: str = ""
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "balance": self.balance,
            "equity": self.equity,
            "margin": self.margin,
            "free_margin": self.free_margin,
            "profit": self.profit,
            "currency": self.currency,
            "leverage": self.leverage,
            "login": self.login,
            "server": self.server,
            "broker": self.broker,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class StandardMargin:
    """Normalized margin information."""
    used: float = 0.0
    free: float = 0.0
    level_pct: float = 0.0
    broker: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "used": self.used,
            "free": self.free,
            "level_pct": self.level_pct,
            "broker": self.broker,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Instrument
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardInstrument:
    """Normalized symbol/instrument metadata."""
    symbol: str
    digits: int = 5
    point: float = 0.00001
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    contract_size: float = 100_000.0
    spread: float = 0.0
    sector: str = "Forex"
    asset_class: str = "forex"
    instrument_type: InstrumentType = InstrumentType.FOREX
    exchange: str = ""
    currency: str = "USD"
    broker: str = ""
    # Aliases used by zohra.py lot-snapping logic
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01

    def __post_init__(self):
        self.volume_min = self.min_lot
        self.volume_max = self.max_lot
        self.volume_step = self.lot_step

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "digits": self.digits,
            "point": self.point,
            "min_lot": self.min_lot,
            "max_lot": self.max_lot,
            "lot_step": self.lot_step,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "contract_size": self.contract_size,
            "contract": self.contract_size,
            "spread": self.spread,
            "sector": self.sector,
            "asset_class": self.asset_class,
            "instrument_type": self.instrument_type.value,
            "exchange": self.exchange,
            "currency": self.currency,
            "broker": self.broker,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Order
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardOrder:
    """Normalized order request/response."""
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    volume: float = 0.01
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    order_id: str = field(default_factory=_new_id)
    broker_order_id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    filled_volume: float = 0.0
    filled_price: float = 0.0
    deviation: int = 10
    magic: int = 0
    comment: str = ""
    broker: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    expiration: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def direction(self) -> str:
        """Backward-compatible direction string."""
        return "LONG" if self.side == OrderSide.BUY else "SHORT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "broker_order_id": self.broker_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "direction": self.direction,
            "order_type": self.order_type.value,
            "volume": self.volume,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status.value,
            "filled_volume": self.filled_volume,
            "filled_price": self.filled_price,
            "magic": self.magic,
            "comment": self.comment,
            "broker": self.broker,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Trade
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardTrade:
    """Normalized completed/historical trade."""
    trade_id: str = field(default_factory=_new_id)
    order_id: str = ""
    symbol: str = ""
    direction: str = "LONG"
    entry_price: float = 0.0
    exit_price: float = 0.0
    volume: float = 0.0
    pnl: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    open_time: datetime = field(default_factory=_utcnow)
    close_time: Optional[datetime] = None
    broker: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "volume": self.volume,
            "pnl": self.pnl,
            "commission": self.commission,
            "swap": self.swap,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat() if self.close_time else None,
            "broker": self.broker,
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Position
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardPosition:
    """Normalized open position."""
    position_id: str = ""
    ticket: int = 0
    symbol: str = ""
    direction: str = "LONG"
    volume: float = 0.0
    lots: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    profit: float = 0.0
    magic: int = 0
    comment: str = ""
    open_time: str = ""
    broker: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Keep lots/volume in sync
        if self.lots == 0.0 and self.volume > 0.0:
            self.lots = self.volume
        elif self.volume == 0.0 and self.lots > 0.0:
            self.volume = self.lots
        # Keep pnl/profit in sync
        if self.profit == 0.0 and self.pnl != 0.0:
            self.profit = self.pnl
        elif self.pnl == 0.0 and self.profit != 0.0:
            self.pnl = self.profit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "ticket": self.ticket,
            "symbol": self.symbol,
            "direction": self.direction,
            "volume": self.volume,
            "lots": self.lots,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "pnl": self.pnl,
            "profit": self.profit,
            "magic": self.magic,
            "comment": self.comment,
            "open_time": self.open_time,
            "broker": self.broker,
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Execution (Confirmation)
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardExecution:
    """Normalized execution confirmation from broker."""
    execution_id: str = field(default_factory=_new_id)
    order_id: str = ""
    ticket: int = 0
    symbol: str = ""
    direction: str = "LONG"
    fill_price: float = 0.0
    fill_volume: float = 0.0
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    pnl: float = 0.0
    latency_ms: float = 0.0
    broker: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "order_id": self.order_id,
            "ticket": self.ticket,
            "symbol": self.symbol,
            "direction": self.direction,
            "fill_price": self.fill_price,
            "fill_volume": self.fill_volume,
            "status": self.status.value,
            "success": self.success,
            "pnl": self.pnl,
            "latency_ms": self.latency_ms,
            "broker": self.broker,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
        }


# ════════════════════════════════════════════════════════════════
#  Standard Portfolio
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardPortfolio:
    """Normalized portfolio summary across positions."""
    total_positions: int = 0
    total_pnl: float = 0.0
    total_volume: float = 0.0
    positions: List[StandardPosition] = field(default_factory=list)
    balance: Optional[StandardBalance] = None
    broker: str = ""
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_positions": self.total_positions,
            "total_pnl": self.total_pnl,
            "total_volume": self.total_volume,
            "positions": [p.to_dict() for p in self.positions],
            "balance": self.balance.to_dict() if self.balance else None,
            "broker": self.broker,
            "timestamp": self.timestamp.isoformat(),
        }


# ════════════════════════════════════════════════════════════════
#  Broker Error
# ════════════════════════════════════════════════════════════════

@dataclass
class BrokerError:
    """Normalized broker error."""
    code: int = 0
    message: str = ""
    broker: str = ""
    retryable: bool = False
    raw_error: Any = None
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "broker": self.broker,
            "retryable": self.retryable,
            "raw_error": str(self.raw_error) if self.raw_error else None,
            "timestamp": self.timestamp.isoformat(),
        }


# ════════════════════════════════════════════════════════════════
#  News Event
# ════════════════════════════════════════════════════════════════

@dataclass
class StandardNewsEvent:
    """Normalized economic news/event."""
    event_id: str = field(default_factory=_new_id)
    title: str = ""
    currency: str = ""
    impact: str = "low"  # low, medium, high
    forecast: str = ""
    actual: str = ""
    previous: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "currency": self.currency,
            "impact": self.impact,
            "forecast": self.forecast,
            "actual": self.actual,
            "previous": self.previous,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }
