"""
╔══════════════════════════════════════════════════════════════════════╗
║   PHASE 7 — TRADE FORENSICS CENTER                                   ║
║   Logs every trade decision: accepted AND rejected.                  ║
║   Enables post-mortem analysis of WHY setups were rejected.          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import sqlite3
import datetime as dt
from typing import Dict, List, Optional, Any

logger = logging.getLogger("zohra.learning.forensics")


class TradeForensics:
    """
    Trade Forensics Center for Zohra Trading OS.

    Captures and stores the FULL context of every trading decision:
    - Executed trades (outcome tracking)
    - Rejected setups (with rejection reason, score, indicators)

    This enables:
    - Post-mortem analysis: "Why did we miss that winning setup?"
    - Rejection audit: "How many good trades did we reject because of news blackout?"
    - Filter tuning: "Are our filters too strict for Gold in London session?"
    """

    def __init__(self, db_path: str = None):
        from zohra.config.settings import settings
        self.db_path = db_path or settings.DB_PATH
        self._init_tables()

    def _init_tables(self):
        """Create forensics tables if they don't exist."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")

            # Rejected trade log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_rejections (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp          TEXT NOT NULL,
                    symbol             TEXT NOT NULL,
                    direction          TEXT NOT NULL,
                    strategy           TEXT NOT NULL,
                    regime             TEXT DEFAULT '',
                    session            TEXT DEFAULT '',
                    confidence_score   REAL DEFAULT 0,
                    rejection_reason   TEXT NOT NULL,
                    reason_for_rejection TEXT DEFAULT '',
                    rejection_category TEXT NOT NULL,
                    entry_price        REAL DEFAULT 0,
                    stop_loss          REAL DEFAULT 0,
                    take_profit        REAL DEFAULT 0,
                    indicators_json    TEXT DEFAULT '{}',
                    scores_json        TEXT DEFAULT '{}',
                    news_status        TEXT DEFAULT 'CLEAR',
                    vol_ratio          REAL DEFAULT 1.0,
                    would_have_won     INTEGER DEFAULT NULL,
                    actual_outcome_pnl REAL DEFAULT NULL,
                    reviewed           INTEGER DEFAULT 0
                )
            """)

            # Schema Migration: Add missing columns if trade_rejections was pre-existing
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(trade_rejections)")
            existing_cols = [row[1] for row in cursor.fetchall()]
            if existing_cols:
                cols_to_add = {
                    "strategy": "TEXT NOT NULL DEFAULT 'unknown'",
                    "rejection_reason": "TEXT NOT NULL DEFAULT ''",
                    "reason_for_rejection": "TEXT NOT NULL DEFAULT ''",
                    "rejection_category": "TEXT NOT NULL DEFAULT 'FILTER'",
                    "regime": "TEXT DEFAULT ''",
                    "session": "TEXT DEFAULT ''",
                    "confidence_score": "REAL DEFAULT 0",
                    "entry_price": "REAL DEFAULT 0",
                    "stop_loss": "REAL DEFAULT 0",
                    "take_profit": "REAL DEFAULT 0",
                    "indicators_json": "TEXT DEFAULT '{}'",
                    "scores_json": "TEXT DEFAULT '{}'",
                    "news_status": "TEXT DEFAULT 'CLEAR'",
                    "vol_ratio": "REAL DEFAULT 1.0",
                    "would_have_won": "INTEGER DEFAULT NULL",
                    "actual_outcome_pnl": "REAL DEFAULT NULL",
                    "reviewed": "INTEGER DEFAULT 0"
                }
                for col_name, col_def in cols_to_add.items():
                    if col_name not in existing_cols:
                        try:
                            conn.execute(f"ALTER TABLE trade_rejections ADD COLUMN {col_name} {col_def}")
                            logger.info(f"Migration: Added missing column {col_name} to trade_rejections.")
                        except Exception as migration_err:
                            logger.error(f"Migration error adding {col_name} to trade_rejections: {migration_err}")

            # Create indexes on trade_rejections after columns are migrated
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rejections_sym
                ON trade_rejections(symbol, timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rejections_cat
                ON trade_rejections(rejection_category, strategy)
            """)

            # Trade decision audit trail
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_decisions (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp         TEXT NOT NULL,
                    symbol            TEXT NOT NULL,
                    direction         TEXT NOT NULL,
                    strategy          TEXT NOT NULL,
                    decision          TEXT NOT NULL,
                    confidence_score  REAL DEFAULT 0,
                    regime            TEXT DEFAULT '',
                    session           TEXT DEFAULT '',
                    entry_price       REAL DEFAULT 0,
                    stop_loss         REAL DEFAULT 0,
                    take_profit       REAL DEFAULT 0,
                    rejection_reason  TEXT DEFAULT '',
                    context_json      TEXT DEFAULT '{}'
                )
            """)

            # Schema Migration: Add missing columns if trade_decisions was pre-existing
            cursor.execute("PRAGMA table_info(trade_decisions)")
            existing_dec_cols = [row[1] for row in cursor.fetchall()]
            if existing_dec_cols:
                dec_cols_to_add = {
                    "strategy": "TEXT NOT NULL DEFAULT 'unknown'",
                    "regime": "TEXT DEFAULT ''",
                    "session": "TEXT DEFAULT ''",
                    "entry_price": "REAL DEFAULT 0",
                    "stop_loss": "REAL DEFAULT 0",
                    "take_profit": "REAL DEFAULT 0",
                    "rejection_reason": "TEXT DEFAULT ''",
                    "context_json": "TEXT DEFAULT '{}'"
                }
                for col_name, col_def in dec_cols_to_add.items():
                    if col_name not in existing_dec_cols:
                        try:
                            conn.execute(f"ALTER TABLE trade_decisions ADD COLUMN {col_name} {col_def}")
                            logger.info(f"Migration: Added missing column {col_name} to trade_decisions.")
                        except Exception as migration_err:
                            logger.error(f"Migration error adding {col_name} to trade_decisions: {migration_err}")

            # Create indexes on trade_decisions after columns are migrated
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_sym
                ON trade_decisions(symbol, decision, timestamp)
            """)

            conn.commit()
            conn.close()
            logger.info("🔬 Trade Forensics Center initialized.")
        except Exception as e:
            logger.error(f"Forensics init error: {e}")

    # ──────────────────────────────────────────────
    #  LOGGING API
    # ──────────────────────────────────────────────

    def log_rejection(
        self,
        symbol: str,
        direction: str,
        strategy: str,
        confidence_score: float,
        rejection_reason: str,
        reason_for_rejection: str = "",
        rejection_category: str = "FILTER",
        regime: str = "",
        session: str = "",
        entry_price: float = 0,
        stop_loss: float = 0,
        take_profit: float = 0,
        indicators: Dict = None,
        scores: Dict = None,
        news_status: str = "CLEAR",
        vol_ratio: float = 1.0
    ):
        """
        Log a rejected trade setup with full context.

        Rejection categories:
            SCORE      — Confidence score below threshold
            NEWS       — News blackout active
            FILTER     — Failed a filter condition (RRR, spread, session, etc.)
            RISK       — Risk agent vetoed the trade
            DUPLICATE  — Similar trade already active
            COOLDOWN   — Symbol or strategy on cooldown
            REGIME     — Market regime not suitable
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("""
                INSERT INTO trade_rejections
                (timestamp, symbol, direction, strategy, regime, session,
                 confidence_score, rejection_reason, reason_for_rejection, rejection_category,
                 entry_price, stop_loss, take_profit,
                 indicators_json, scores_json, news_status, vol_ratio)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                dt.datetime.utcnow().isoformat(),
                symbol, direction, strategy, regime, session,
                confidence_score, rejection_reason, reason_for_rejection, rejection_category,
                entry_price, stop_loss, take_profit,
                json.dumps(indicators or {}),
                json.dumps(scores or {}),
                news_status, vol_ratio
            ))
            conn.commit()
            conn.close()
            logger.debug(f"🔬 Rejection logged: {symbol} {direction} via {strategy} — {rejection_reason}")
        except Exception as e:
            logger.error(f"Failed to log rejection: {e}")

    def log_decision(
        self,
        symbol: str,
        direction: str,
        strategy: str,
        decision: str,
        confidence_score: float = 0,
        regime: str = "",
        session: str = "",
        entry_price: float = 0,
        stop_loss: float = 0,
        take_profit: float = 0,
        rejection_reason: str = "",
        context: Dict = None
    ):
        """
        Log a trade decision to the audit trail (ACCEPTED, REJECTED, or VETOED).
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("""
                INSERT INTO trade_decisions
                (timestamp, symbol, direction, strategy, decision,
                 confidence_score, regime, session,
                 entry_price, stop_loss, take_profit,
                 rejection_reason, context_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                dt.datetime.utcnow().isoformat(),
                symbol, direction, strategy, decision,
                confidence_score, regime, session,
                entry_price, stop_loss, take_profit,
                rejection_reason,
                json.dumps(context or {})
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_rejections(
        self,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        category: Optional[str] = None,
        since_hours: int = 24,
        limit: int = 100
    ) -> List[Dict]:
        """Query recent rejections with optional filters."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            since = (dt.datetime.utcnow() - dt.timedelta(hours=since_hours)).isoformat()
            q = "SELECT * FROM trade_rejections WHERE timestamp >= ?"
            params: List[Any] = [since]

            if symbol:
                q += " AND symbol=?"
                params.append(symbol)
            if strategy:
                q += " AND strategy=?"
                params.append(strategy)
            if category:
                q += " AND rejection_category=?"
                params.append(category)

            q += f" ORDER BY timestamp DESC LIMIT {int(limit)}"
            cursor.execute(q, params)
            rows = cursor.fetchall()
            conn.close()

            results = []
            for r in rows:
                d = dict(r)
                for field in ("indicators_json", "scores_json"):
                    if field in d and isinstance(d[field], str):
                        try:
                            d[field] = json.loads(d[field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                results.append(d)
            return results
        except Exception as e:
            logger.error(f"Rejection query error: {e}")
            return []

    def get_rejection_stats(self, since_hours: int = 168) -> Dict:
        """
        Get rejection statistics (last 7 days by default).
        Returns breakdown by category, strategy, and symbol.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            since = (dt.datetime.utcnow() - dt.timedelta(hours=since_hours)).isoformat()

            cursor = conn.cursor()

            # Total rejections
            cursor.execute(
                "SELECT COUNT(*) FROM trade_rejections WHERE timestamp >= ?", (since,)
            )
            total = cursor.fetchone()[0]

            # By category
            cursor.execute("""
                SELECT rejection_category, COUNT(*) as cnt
                FROM trade_rejections WHERE timestamp >= ?
                GROUP BY rejection_category ORDER BY cnt DESC
            """, (since,))
            by_category = {row[0]: row[1] for row in cursor.fetchall()}

            # By strategy
            cursor.execute("""
                SELECT strategy, COUNT(*) as cnt
                FROM trade_rejections WHERE timestamp >= ?
                GROUP BY strategy ORDER BY cnt DESC
            """, (since,))
            by_strategy = {row[0]: row[1] for row in cursor.fetchall()}

            # By symbol
            cursor.execute("""
                SELECT symbol, COUNT(*) as cnt
                FROM trade_rejections WHERE timestamp >= ?
                GROUP BY symbol ORDER BY cnt DESC
            """, (since,))
            by_symbol = {row[0]: row[1] for row in cursor.fetchall()}

            # Average rejected score
            cursor.execute(
                "SELECT AVG(confidence_score) FROM trade_rejections WHERE timestamp >= ?", (since,)
            )
            avg_rejected_score = cursor.fetchone()[0] or 0

            conn.close()

            return {
                "period_hours": since_hours,
                "total_rejections": total,
                "avg_rejected_score": round(avg_rejected_score, 2),
                "by_category": by_category,
                "by_strategy": by_strategy,
                "by_symbol": by_symbol
            }
        except Exception as e:
            logger.error(f"Rejection stats error: {e}")
            return {"error": str(e)}

    def get_decisions(
        self,
        symbol: Optional[str] = None,
        decision: Optional[str] = None,
        since_hours: int = 24,
        limit: int = 100
    ) -> List[Dict]:
        """Query the decision audit trail."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            since = (dt.datetime.utcnow() - dt.timedelta(hours=since_hours)).isoformat()
            q = "SELECT * FROM trade_decisions WHERE timestamp >= ?"
            params: List[Any] = [since]

            if symbol:
                q += " AND symbol=?"
                params.append(symbol)
            if decision:
                q += " AND decision=?"
                params.append(decision)

            q += f" ORDER BY timestamp DESC LIMIT {int(limit)}"
            cursor.execute(q, params)
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Decision query error: {e}")
            return []

    def get_missed_winners(self, since_hours: int = 168) -> List[Dict]:
        """
        Return rejections that we later determined would have been winners.
        Useful for identifying overly aggressive filters.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            since = (dt.datetime.utcnow() - dt.timedelta(hours=since_hours)).isoformat()
            cursor.execute("""
                SELECT * FROM trade_rejections
                WHERE timestamp >= ? AND would_have_won = 1
                ORDER BY actual_outcome_pnl DESC LIMIT 50
            """, (since,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Missed winners query error: {e}")
            return []


# Singleton
trade_forensics = TradeForensics()
