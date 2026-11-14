"""
Rejected opportunity logging.
Extracted from zohra_enhanced_core + analyze_rejections workflow.
"""

from typing import List, Optional

from zohra.core.models import RejectedTradeRecord
from zohra.db.repositories.rejections import RejectionRepository


class RejectionLogger:
    """Persists every rejected setup with full diagnostic context."""

    def __init__(self, repo: Optional[RejectionRepository] = None):
        self.repo = repo or RejectionRepository()

    def log(self, record: RejectedTradeRecord) -> int:
        return self.repo.insert(record.to_db_dict())

    def log_simple(
        self,
        symbol: str,
        confidence_score: float,
        failed_conditions: List[str],
        reason_for_rejection: str,
        **kwargs,
    ) -> int:
        record = RejectedTradeRecord(
            symbol=symbol,
            confidence_score=confidence_score,
            failed_conditions=failed_conditions,
            reason_for_rejection=reason_for_rejection,
            session=kwargs.get("session"),
            market_regime=kwargs.get("market_regime"),
            strategy=kwargs.get("strategy"),
            news_status=kwargs.get("news_status"),
            score_breakdown=kwargs.get("score_breakdown", {}),
            metadata=kwargs.get("metadata", {}),
        )
        return self.log(record)
