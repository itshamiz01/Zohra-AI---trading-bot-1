"""Equity curve persistence."""

from datetime import datetime
from typing import Dict, List, Optional

from zohra.db.connection import DatabaseConnection, get_db


class EquityRepository:
    def __init__(self, db: Optional[DatabaseConnection] = None):
        self.db = db or get_db()

    def log_snapshot(
        self,
        equity: float,
        open_pnl: float = 0,
        daily_pnl: float = 0,
        monthly_pnl: float = 0,
        drawdown_pct: float = 0,
        broker: str = "mt5",
    ):
        p = self.db.placeholder()
        sql = f"""
            INSERT INTO equity_curve
            (timestamp, equity, open_pnl, daily_pnl, monthly_pnl, drawdown_pct, broker)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p})
        """
        with self.db.cursor() as cur:
            cur.execute(sql, [
                datetime.utcnow().isoformat(),
                equity, open_pnl, daily_pnl, monthly_pnl, drawdown_pct, broker,
            ])

    def get_curve(self, since: Optional[str] = None, limit: int = 1000) -> List[Dict]:
        p = self.db.placeholder()
        params: list = []
        where = ""
        if since:
            where = f"WHERE timestamp >= {p}"
            params.append(since)
        sql = f"SELECT * FROM equity_curve {where} ORDER BY timestamp ASC LIMIT {limit}"
        with self.db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) if isinstance(r, dict) else {"timestamp": r[1], "equity": r[2]} for r in rows]
