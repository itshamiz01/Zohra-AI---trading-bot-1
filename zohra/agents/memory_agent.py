from typing import Dict, Any
from zohra.db.schema import db

class MemoryAgent:
    """
    Memory Agent:
    - Stores every trade, decision, and rejection.
    - Interacts with the central ZohraDatabase instance (db).
    - Builds a proprietary dataset of agent audits and votes.
    """
    def __init__(self):
        self.db = db

    def log_trade(self, trade_dict: Dict[str, Any]) -> bool:
        """Stores an opened trade in the database."""
        return self.db.log_trade_open(trade_dict)

    def log_trade_close(self, trade_id: str, exit_price: float, pnl_usd: float,
                        pnl_pct: float, exit_reason: str, exit_code: str = "",
                        duration_minutes: int = 0) -> bool:
        """Stores a closed trade record."""
        return self.db.log_trade_close(
            trade_id=trade_id,
            exit_price=exit_price,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            exit_code=exit_code,
            duration_minutes=duration_minutes
        )

    def log_decision(self, decision: Dict[str, Any]) -> bool:
        """Stores an agent consensus decision in the agent_decisions table."""
        return self.db.log_agent_decision(decision)

    def log_rejection(self, rejection: Dict[str, Any]) -> bool:
        """Stores a rejected trade setup in the rejected_trades table."""
        return self.db.log_rejection(rejection)
