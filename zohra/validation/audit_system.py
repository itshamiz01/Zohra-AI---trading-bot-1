"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — TRADE REPLAY & AUDIT SYSTEM                     ║
║     Regulatory-Grade Forensic Audits & Trade Playback Logs           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any

from zohra.config.settings import settings

logger = logging.getLogger("zohra.validation.audit")


class TradeAuditSystem:
    """
    Forensic auditing library that maps the absolute timeline of a trade:
    entry analysis, execution slippages, latency spikes, and exit reasons.
    """

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """Initialize database table for trade audits."""
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_audits (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    pnl REAL,
                    execution_details TEXT NOT NULL,  -- JSON payload
                    context_snapshot TEXT NOT NULL,   -- JSON payload
                    lessons_learned TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error creating audit system database: {e}")

    def create_audit_record(self, ticket: int, symbol: str, direction: str,
                            opened_at: datetime, execution_details: Dict[str, Any],
                            context_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new trade audit record on entry fill."""
        exec_str = json.dumps(execution_details)
        ctx_str = json.dumps(context_snapshot)

        record = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "opened_at": opened_at.isoformat(),
            "closed_at": None,
            "pnl": 0.0,
            "execution_details": execution_details,
            "context_snapshot": context_snapshot,
            "lessons_learned": ""
        }

        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO trade_audits 
                (ticket, symbol, direction, opened_at, execution_details, context_snapshot, pnl)
                VALUES (?, ?, ?, ?, ?, ?, 0.0)
            """, (ticket, symbol, direction, opened_at.isoformat(), exec_str, ctx_str))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to insert audit record: {e}")

        return record

    def finalize_audit_record(self, ticket: int, closed_at: datetime, 
                              pnl: float, lessons: str = "") -> bool:
        """Appends exit parameters and forensic lessons to a trade audit."""
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trade_audits 
                SET closed_at = ?, pnl = ?, lessons_learned = ?
                WHERE ticket = ?
            """, (closed_at.isoformat(), pnl, lessons, ticket))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to finalize trade audit: {e}")
            return False

    def get_audit(self, ticket: int) -> Optional[Dict[str, Any]]:
        """Fetch forensic trade audit trail by ticket ID."""
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_audits WHERE ticket = ?", (ticket,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "ticket": row["ticket"],
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "opened_at": row["opened_at"],
                    "closed_at": row["closed_at"],
                    "pnl": row["pnl"],
                    "execution_details": json.loads(row["execution_details"]),
                    "context_snapshot": json.loads(row["context_snapshot"]),
                    "lessons_learned": row["lessons_learned"]
                }
        except Exception as e:
            logger.error(f"Failed to query audit trail: {e}")
        return None

    def list_audits(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List audit ledger records."""
        results = []
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticket, symbol, direction, opened_at, closed_at, pnl, lessons_learned 
                FROM trade_audits ORDER BY opened_at DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            conn.close()
            
            for row in rows:
                results.append({
                    "ticket": row["ticket"],
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "opened_at": row["opened_at"],
                    "closed_at": row["closed_at"],
                    "pnl": row["pnl"],
                    "lessons_learned": row["lessons_learned"]
                })
        except Exception as e:
            logger.error(f"Failed to fetch audits: {e}")
        return results


# Singleton
audit_system = TradeAuditSystem()
