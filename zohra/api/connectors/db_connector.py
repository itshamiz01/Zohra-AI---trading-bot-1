import logging
from typing import List, Dict, Any, Optional
from zohra.db.schema import db

logger = logging.getLogger("zohra.api.connectors.db")

class DBConnector:
    """
    Data connector for fetching trade records, decisions,
    rejections, and audit trails from the database.
    """

    def get_recent_trades(self, limit: int = 10, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch closed trades from history."""
        try:
            return db.get_closed_trades(limit=limit, symbol=symbol)
        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []

    def get_open_trades(self) -> List[Dict[str, Any]]:
        """Fetch active trades from database."""
        try:
            return db.get_open_trades()
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            return []

    def get_recent_rejections(self, limit: int = 10, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch recent rejected trade opportunities."""
        try:
            return db.get_rejections(limit=limit, symbol=symbol)
        except Exception as e:
            logger.error(f"Error getting recent rejections: {e}")
            return []

    def get_latest_rejection_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch the single most recent rejection log for a symbol."""
        try:
            rejections = db.get_rejections(limit=1, symbol=symbol)
            return rejections[0] if rejections else None
        except Exception as e:
            logger.error(f"Error getting latest rejection for {symbol}: {e}")
            return None

    def get_latest_trade_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch the single most recent trade record for a symbol."""
        try:
            # We fetch both open and closed, checking which is newer
            open_trades = [t for t in self.get_open_trades() if t.get('symbol', '').upper() == symbol.upper()]
            closed_trades = db.get_closed_trades(limit=1, symbol=symbol)
            
            candidates = []
            if open_trades:
                candidates.append((open_trades[0], open_trades[0].get('timestamp_open', '')))
            if closed_trades:
                candidates.append((closed_trades[0], closed_trades[0].get('timestamp_close', '')))
                
            if not candidates:
                return None
            
            # Sort by timestamp descending
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]
        except Exception as e:
            logger.error(f"Error getting latest trade for {symbol}: {e}")
            return None

    def get_recent_decisions(self, limit: int = 10, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch recent multi-agent voting decisions."""
        try:
            query = "SELECT * FROM agent_decisions"
            params = []
            if symbol:
                query += " WHERE symbol = ?"
                params.append(symbol)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            return db._execute(query, tuple(params), fetch="all") or []
        except Exception as e:
            logger.error(f"Error getting recent decisions: {e}")
            return []

    def get_decision_by_proposal_id(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Fetch multi-agent voting details by proposal ID."""
        try:
            query = "SELECT * FROM agent_decisions WHERE proposal_id = ?"
            return db._execute(query, (proposal_id,), fetch="one")
        except Exception as e:
            logger.error(f"Error getting decision for proposal {proposal_id}: {e}")
            return None
