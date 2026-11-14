"""
Automatic trade logging service.
Called by executor / strategy on every open and close.
"""

from datetime import datetime
from typing import Optional

from zohra.core.models import TradeRecord
from zohra.db.repositories.trades import TradeRepository


class TradeLogger:
    """Persists complete trade lifecycle to database."""

    def __init__(self, repo: Optional[TradeRepository] = None):
        self.repo = repo or TradeRepository()

    def log_entry(self, trade: TradeRecord) -> str:
        """Save trade on entry. Returns trade_id."""
        data = trade.to_db_dict()
        return self.repo.insert(data)

    def log_exit(
        self,
        trade_id: str,
        exit_price: float,
        profit_loss: float,
        reason_for_exit: str,
    ):
        """Update trade on close."""
        self.repo.close_trade(
            trade_id=trade_id,
            exit_price=exit_price,
            profit_loss=profit_loss,
            reason_for_exit=reason_for_exit,
            timestamp_close=datetime.utcnow().isoformat(),
        )

    def from_mt5_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        confidence_score: float,
        session: str,
        market_regime: str,
        strategy: str,
        news_status: str,
        reason_for_entry: str,
        mt5_ticket: int,
        position_size_lots: float = 0.01,
        risk_usd: float = 0.0,
    ) -> str:
        """Convenience builder from MT5 execution context."""
        from zohra.core.enums import Direction, MarketRegime, NewsStatus, Session, StrategyName

        trade = TradeRecord(
            symbol=symbol,
            direction=Direction(direction),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence_score=confidence_score,
            session=Session(session) if session in Session._value2member_map_ else Session.OFF,
            market_regime=MarketRegime(market_regime) if market_regime in MarketRegime._value2member_map_ else MarketRegime.RANGING,
            strategy=StrategyName(strategy) if strategy in StrategyName._value2member_map_ else StrategyName.MANUAL,
            news_status=NewsStatus(news_status) if news_status in NewsStatus._value2member_map_ else NewsStatus.UNKNOWN,
            reason_for_entry=reason_for_entry,
            mt5_ticket=mt5_ticket,
            position_size_lots=position_size_lots,
            risk_usd=risk_usd,
        )
        return self.log_entry(trade)
