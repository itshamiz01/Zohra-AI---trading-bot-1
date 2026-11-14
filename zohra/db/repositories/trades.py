"""Trade persistence repository."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from zohra.db.connection import DatabaseConnection, get_db


class TradeRepository:
    def __init__(self, db: Optional[DatabaseConnection] = None):
        self.db = db or get_db()

    def insert(self, trade: Dict[str, Any]) -> str:
        p = self.db.placeholder()
        metadata = json.dumps(trade.get("metadata") or {})
        cols = [
            "trade_id", "timestamp_open", "symbol", "direction",
            "entry_price", "stop_loss", "take_profit",
            "confidence_score", "session", "market_regime", "strategy",
            "news_status", "reason_for_entry", "risk_reward_ratio",
            "mt5_ticket", "broker", "asset_class", "position_size_lots",
            "risk_usd", "requested_price", "slippage_points", "entry_spread_points",
            "execution_latency_ms", "metadata",
        ]
        values = [
            trade["trade_id"],
            trade["timestamp_open"],
            trade["symbol"],
            trade["direction"],
            trade["entry_price"],
            trade["stop_loss"],
            trade["take_profit"],
            trade["confidence_score"],
            trade.get("session"),
            trade.get("market_regime"),
            trade["strategy"],
            trade.get("news_status", "unknown"),
            trade["reason_for_entry"],
            trade.get("risk_reward_ratio"),
            trade.get("mt5_ticket"),
            trade.get("broker", "mt5"),
            trade.get("asset_class", "forex"),
            trade.get("position_size_lots", 0.01),
            trade.get("risk_usd", 0),
            trade.get("requested_price"),
            trade.get("slippage_points"),
            trade.get("entry_spread_points"),
            trade.get("execution_latency_ms"),
            metadata,
        ]
        placeholders = ", ".join([p] * len(cols))
        sql = f"INSERT INTO trades ({', '.join(cols)}) VALUES ({placeholders})"
        with self.db.cursor() as cur:
            cur.execute(sql, values)
        return trade["trade_id"]

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        profit_loss: float,
        reason_for_exit: str,
        timestamp_close: Optional[str] = None,
    ):
        p = self.db.placeholder()
        ts = timestamp_close or datetime.utcnow().isoformat()
        sql = f"""
            UPDATE trades SET
                timestamp_close = {p},
                exit_price = {p},
                profit_loss = {p},
                reason_for_exit = {p},
                updated_at = {p}
            WHERE trade_id = {p}
        """
        with self.db.cursor() as cur:
            cur.execute(sql, [ts, exit_price, profit_loss, reason_for_exit, ts, trade_id])

    def get_by_id(self, trade_id: str) -> Optional[Dict]:
        p = self.db.placeholder()
        with self.db.cursor() as cur:
            cur.execute(f"SELECT * FROM trades WHERE trade_id = {p}", [trade_id])
            row = cur.fetchone()
        return self._row_to_dict(row)

    def get_open_trades(self) -> List[Dict]:
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM trades WHERE timestamp_close IS NULL ORDER BY timestamp_open DESC")
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_closed_trades(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict]:
        p = self.db.placeholder()
        clauses = ["timestamp_close IS NOT NULL"]
        params: list = []

        if since:
            clauses.append(f"timestamp_close >= {p}")
            params.append(since)
        if until:
            clauses.append(f"timestamp_close <= {p}")
            params.append(until)
        if symbol:
            clauses.append(f"symbol = {p}")
            params.append(symbol)
        if strategy:
            clauses.append(f"strategy = {p}")
            params.append(strategy)

        sql = f"""
            SELECT * FROM trades
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp_close DESC
            LIMIT {limit}
        """
        with self.db.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row) -> Optional[Dict]:
        if row is None:
            return None
        if isinstance(row, dict):
            d = dict(row)
        elif hasattr(row, "keys"):
            d = {k: row[k] for k in row.keys()}
        else:
            return None
        if "metadata" in d and isinstance(d["metadata"], str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except json.JSONDecodeError:
                pass
        return d
