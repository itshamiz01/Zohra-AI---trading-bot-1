"""Domain models for trades and rejected setups."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from zohra.core.enums import (
    Direction,
    MarketRegime,
    NewsStatus,
    Session,
    StrategyName,
)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _new_trade_id() -> str:
    return f"ZHR-{uuid.uuid4().hex[:12].upper()}"


@dataclass
class TradeRecord:
    """Complete trade record — maps 1:1 to database trades table."""

    symbol: str
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: float
    session: Session
    market_regime: MarketRegime
    strategy: StrategyName
    news_status: NewsStatus
    reason_for_entry: str
    trade_id: str = field(default_factory=_new_trade_id)
    timestamp_open: datetime = field(default_factory=_utc_now)
    timestamp_close: Optional[datetime] = None
    exit_price: Optional[float] = None
    profit_loss: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    reason_for_exit: Optional[str] = None
    mt5_ticket: Optional[int] = None
    broker: str = "mt5"
    asset_class: str = "forex"
    position_size_lots: float = 0.01
    risk_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute_risk_reward(self) -> Optional[float]:
        """Calculate planned R:R from entry, SL, TP."""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        if risk <= 0:
            return None
        return round(reward / risk, 2)

    def to_db_dict(self) -> Dict[str, Any]:
        rr = self.risk_reward_ratio or self.compute_risk_reward()
        return {
            "trade_id": self.trade_id,
            "timestamp_open": self.timestamp_open.isoformat(),
            "timestamp_close": self.timestamp_close.isoformat() if self.timestamp_close else None,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "exit_price": self.exit_price,
            "profit_loss": self.profit_loss,
            "risk_reward_ratio": rr,
            "confidence_score": self.confidence_score,
            "session": self.session.value,
            "market_regime": self.market_regime.value,
            "strategy": self.strategy.value,
            "news_status": self.news_status.value,
            "reason_for_entry": self.reason_for_entry,
            "reason_for_exit": self.reason_for_exit,
            "mt5_ticket": self.mt5_ticket,
            "broker": self.broker,
            "asset_class": self.asset_class,
            "position_size_lots": self.position_size_lots,
            "risk_usd": self.risk_usd,
            "metadata": self.metadata,
        }


@dataclass
class RejectedTradeRecord:
    """Rejected opportunity — maps to rejected_trades table."""

    symbol: str
    confidence_score: float
    failed_conditions: List[str]
    reason_for_rejection: str
    timestamp: datetime = field(default_factory=_utc_now)
    session: Optional[Session] = None
    market_regime: Optional[MarketRegime] = None
    strategy: Optional[StrategyName] = None
    news_status: Optional[NewsStatus] = None
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_db_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "confidence_score": self.confidence_score,
            "failed_conditions": self.failed_conditions,
            "reason_for_rejection": self.reason_for_rejection,
            "session": self.session.value if self.session else None,
            "market_regime": self.market_regime.value if self.market_regime else None,
            "strategy": self.strategy.value if self.strategy else None,
            "news_status": self.news_status.value if self.news_status else None,
            "score_breakdown": self.score_breakdown,
            "metadata": self.metadata,
        }
