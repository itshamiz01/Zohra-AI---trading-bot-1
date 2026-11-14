"""
╔══════════════════════════════════════════════════════════════════════╗
║   PHASE 1 — KNOWLEDGE INGESTION ENGINE                               ║
║   Stores trading knowledge from any source as structured strategies. ║
║   Queryable by category, market type, timeframe, and session.        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import sqlite3
import datetime as dt
from typing import Dict, List, Optional, Any

logger = logging.getLogger("zohra.learning.knowledge_base")


class StrategyKnowledgeBase:
    """
    Persistent knowledge store for ingested trading strategies.

    Every strategy (from YouTube, books, PDFs, courses, research papers, etc.)
    is converted into a structured record that Zohra can query at runtime.

    Schema per strategy:
        strategy_name, category, market_type, timeframes, entry_rules,
        exit_rules, risk_rules, session_rules, source, source_url,
        notes, is_active, created_at, updated_at
    """

    VALID_CATEGORIES = [
        "SMC", "TrendFollowing", "MeanReversion", "Breakout",
        "Scalping", "Reversal", "Volatility", "ChartPattern",
        "PriceAction", "Custom"
    ]

    VALID_MARKET_TYPES = [
        "Trending", "Ranging", "Breakout", "Volatile", "All"
    ]

    def __init__(self, db_path: str = None):
        from zohra.config.settings import settings
        self.db_path = db_path or settings.DB_PATH
        self._init_table()

    def _init_table(self):
        """Create the knowledge base table if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_knowledge_base (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name   TEXT NOT NULL UNIQUE,
                    category        TEXT NOT NULL,
                    market_type     TEXT NOT NULL DEFAULT 'All',
                    timeframes      TEXT NOT NULL DEFAULT '[]',
                    entry_rules     TEXT NOT NULL DEFAULT '[]',
                    exit_rules      TEXT NOT NULL DEFAULT '[]',
                    risk_rules      TEXT NOT NULL DEFAULT '[]',
                    session_rules   TEXT NOT NULL DEFAULT '[]',
                    source          TEXT DEFAULT 'Manual',
                    source_url      TEXT DEFAULT '',
                    notes           TEXT DEFAULT '',
                    is_active       INTEGER DEFAULT 1,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_skb_category
                ON strategy_knowledge_base(category, is_active)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_skb_market_type
                ON strategy_knowledge_base(market_type, is_active)
            """)
            conn.commit()
            conn.close()
            logger.info("📚 Strategy Knowledge Base initialized.")
        except Exception as e:
            logger.error(f"Error initializing Strategy Knowledge Base: {e}")

    # ──────────────────────────────────────────────
    #  INGESTION API
    # ──────────────────────────────────────────────

    def add_strategy(
        self,
        strategy_name: str,
        category: str,
        market_type: str = "All",
        timeframes: List[str] = None,
        entry_rules: List[str] = None,
        exit_rules: List[str] = None,
        risk_rules: List[str] = None,
        session_rules: List[str] = None,
        source: str = "Manual",
        source_url: str = "",
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Ingest a new strategy into the knowledge base.

        Returns:
            dict with status and strategy_id
        """
        if category not in self.VALID_CATEGORIES:
            return {"status": "error", "error": f"Invalid category '{category}'. Valid: {self.VALID_CATEGORIES}"}
        if market_type not in self.VALID_MARKET_TYPES:
            return {"status": "error", "error": f"Invalid market_type '{market_type}'. Valid: {self.VALID_MARKET_TYPES}"}

        now = dt.datetime.utcnow().isoformat()
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO strategy_knowledge_base
                (strategy_name, category, market_type, timeframes, entry_rules,
                 exit_rules, risk_rules, session_rules, source, source_url, notes,
                 is_active, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)
            """, (
                strategy_name,
                category,
                market_type,
                json.dumps(timeframes or []),
                json.dumps(entry_rules or []),
                json.dumps(exit_rules or []),
                json.dumps(risk_rules or []),
                json.dumps(session_rules or []),
                source,
                source_url,
                notes,
                now, now
            ))
            conn.commit()
            strategy_id = cursor.lastrowid
            conn.close()
            logger.info(f"📚 Knowledge ingested: '{strategy_name}' ({category}/{market_type})")
            return {"status": "success", "strategy_id": strategy_id, "name": strategy_name}
        except Exception as e:
            logger.error(f"Failed to add strategy: {e}")
            return {"status": "error", "error": str(e)}

    def bulk_ingest(self, strategies: List[Dict]) -> Dict:
        """Ingest multiple strategies at once."""
        results = {"ingested": 0, "errors": 0, "details": []}
        for s in strategies:
            res = self.add_strategy(**s)
            if res["status"] == "success":
                results["ingested"] += 1
            else:
                results["errors"] += 1
            results["details"].append(res)
        return results

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_all(self, active_only: bool = True) -> List[Dict]:
        """Return all strategies from the knowledge base."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            q = "SELECT * FROM strategy_knowledge_base"
            if active_only:
                q += " WHERE is_active=1"
            q += " ORDER BY category, strategy_name"
            cursor.execute(q)
            rows = cursor.fetchall()
            conn.close()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error querying knowledge base: {e}")
            return []

    def get_by_category(self, category: str, active_only: bool = True) -> List[Dict]:
        """Return strategies filtered by category."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            q = "SELECT * FROM strategy_knowledge_base WHERE category=?"
            params = [category]
            if active_only:
                q += " AND is_active=1"
            cursor.execute(q, params)
            rows = cursor.fetchall()
            conn.close()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error querying by category: {e}")
            return []

    def get_by_market_type(self, market_type: str) -> List[Dict]:
        """Return strategies applicable to a market type."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM strategy_knowledge_base WHERE (market_type=? OR market_type='All') AND is_active=1",
                (market_type,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error querying by market type: {e}")
            return []

    def search(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Full-text search across strategy names, notes, and rules."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            pattern = f"%{keyword}%"
            cursor.execute("""
                SELECT * FROM strategy_knowledge_base
                WHERE (strategy_name LIKE ? OR notes LIKE ? OR entry_rules LIKE ?
                       OR category LIKE ? OR source LIKE ?)
                AND is_active=1
                ORDER BY strategy_name LIMIT ?
            """, (pattern, pattern, pattern, pattern, pattern, limit))
            rows = cursor.fetchall()
            conn.close()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def get_by_name(self, strategy_name: str) -> Optional[Dict]:
        """Get a single strategy by name."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM strategy_knowledge_base WHERE strategy_name=?",
                (strategy_name,)
            )
            row = cursor.fetchone()
            conn.close()
            return self._row_to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Get by name error: {e}")
            return None

    # ──────────────────────────────────────────────
    #  MANAGEMENT API
    # ──────────────────────────────────────────────

    def deactivate(self, strategy_name: str) -> bool:
        """Soft-delete a strategy by marking it inactive."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute(
                "UPDATE strategy_knowledge_base SET is_active=0, updated_at=? WHERE strategy_name=?",
                (dt.datetime.utcnow().isoformat(), strategy_name)
            )
            conn.commit()
            conn.close()
            logger.info(f"📚 Strategy deactivated: '{strategy_name}'")
            return True
        except Exception as e:
            logger.error(f"Deactivation error: {e}")
            return False

    def reactivate(self, strategy_name: str) -> bool:
        """Re-enable a previously deactivated strategy."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute(
                "UPDATE strategy_knowledge_base SET is_active=1, updated_at=? WHERE strategy_name=?",
                (dt.datetime.utcnow().isoformat(), strategy_name)
            )
            conn.commit()
            conn.close()
            logger.info(f"📚 Strategy reactivated: '{strategy_name}'")
            return True
        except Exception as e:
            logger.error(f"Reactivation error: {e}")
            return False

    def get_stats(self) -> Dict:
        """Return summary statistics of the knowledge base."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM strategy_knowledge_base WHERE is_active=1")
            active = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM strategy_knowledge_base WHERE is_active=0")
            inactive = cursor.fetchone()[0]
            cursor.execute(
                "SELECT category, COUNT(*) as cnt FROM strategy_knowledge_base WHERE is_active=1 GROUP BY category"
            )
            by_category = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()
            return {
                "active_strategies": active,
                "inactive_strategies": inactive,
                "by_category": by_category,
                "total": active + inactive
            }
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return {"error": str(e)}

    # ──────────────────────────────────────────────
    #  INTERNAL
    # ──────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row) -> Dict:
        """Convert a sqlite3.Row to a clean dict with parsed JSON fields."""
        d = dict(row)
        for field in ("timeframes", "entry_rules", "exit_rules", "risk_rules", "session_rules"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
        return d


# Singleton
strategy_knowledge_base = StrategyKnowledgeBase()
