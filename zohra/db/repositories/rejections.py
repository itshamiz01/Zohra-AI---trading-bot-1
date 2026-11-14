"""Rejected trade persistence repository."""

import json
from typing import Any, Dict, List, Optional

from zohra.db.connection import DatabaseConnection, get_db


class RejectionRepository:
    def __init__(self, db: Optional[DatabaseConnection] = None):
        self.db = db or get_db()

    def insert(self, record: Dict[str, Any]) -> int:
        p = self.db.placeholder()
        failed = json.dumps(record.get("failed_conditions") or [])
        breakdown = json.dumps(record.get("score_breakdown") or {})
        metadata = json.dumps(record.get("metadata") or {})

        cols = [
            "timestamp", "symbol", "confidence_score", "failed_conditions",
            "reason_for_rejection", "session", "market_regime", "strategy",
            "news_status", "score_breakdown", "metadata",
        ]
        values = [
            record["timestamp"],
            record["symbol"],
            record["confidence_score"],
            failed,
            record["reason_for_rejection"],
            record.get("session"),
            record.get("market_regime"),
            record.get("strategy"),
            record.get("news_status"),
            breakdown,
            metadata,
        ]
        placeholders = ", ".join([p] * len(cols))
        sql = f"INSERT INTO rejected_trades ({', '.join(cols)}) VALUES ({placeholders})"

        with self.db.cursor() as cur:
            cur.execute(sql, values)
            if self.db.backend == "sqlite":
                return cur.lastrowid
            cur.execute("SELECT lastval()")
            return cur.fetchone()["lastval"]

    def get_recent(self, limit: int = 100, symbol: Optional[str] = None) -> List[Dict]:
        p = self.db.placeholder()
        params: list = []
        where = ""
        if symbol:
            where = f"WHERE symbol = {p}"
            params.append(symbol)
        sql = f"""
            SELECT * FROM rejected_trades {where}
            ORDER BY timestamp DESC LIMIT {limit}
        """
        with self.db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count_by_period(self, since: str, until: Optional[str] = None) -> int:
        p = self.db.placeholder()
        params = [since]
        clause = f"timestamp >= {p}"
        if until:
            clause += f" AND timestamp <= {p}"
            params.append(until)
        with self.db.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) as cnt FROM rejected_trades WHERE {clause}", params)
            row = cur.fetchone()
        if isinstance(row, dict):
            return row.get("cnt", 0)
        return row[0] if row else 0

    def _row_to_dict(self, row) -> Dict:
        if isinstance(row, dict):
            d = dict(row)
        else:
            d = dict(row)
        for key in ("failed_conditions", "score_breakdown", "metadata"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except json.JSONDecodeError:
                    pass
        return d
