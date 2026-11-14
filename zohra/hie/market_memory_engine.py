"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 6 — MARKET MEMORY ENGINE                                    ║
║   Gives Zohra persistent memory about market conditions.             ║
║   Stores best/worst session, conditions, and setup results.          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import time
import datetime as dt
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.memory")


class MarketMemoryEngine:
    """
    Builds and serves Zohra's market memory.
    Memory is derived from pattern stats and represents condensed knowledge
    about what works best per symbol, session, and setup combination.

    Example memory entry:
        XAUUSD | BOS+FVG | London | LONG → win_rate=79%, avg_rr=2.7
    """

    def __init__(self):
        from zohra.hie.historical_data_engine import historical_data_engine
        self._db_path = historical_data_engine.db_path_hie
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._memory_cache: Dict = {}
        self._init_table()

    def _init_table(self):
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_market_memory (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol       TEXT NOT NULL,
                    setup_type   TEXT NOT NULL,
                    session      TEXT NOT NULL,
                    direction    TEXT NOT NULL,
                    occurrences  INTEGER DEFAULT 0,
                    win_rate     REAL DEFAULT 0,
                    avg_rr       REAL DEFAULT 0,
                    memory_label TEXT,
                    is_strong    INTEGER DEFAULT 0,
                    is_weak      INTEGER DEFAULT 0,
                    updated_at   TEXT NOT NULL,
                    UNIQUE(symbol, setup_type, session, direction)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_sym ON hie_market_memory(symbol, session)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"MarketMemory init error: {e}")

    # ──────────────────────────────────────────────
    #  BACKGROUND REFRESH
    # ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-Memory")
        self._thread.start()
        logger.info("🧠 HIE Market Memory Engine started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                self.refresh_memory()
            except Exception as e:
                logger.error(f"MarketMemory refresh error: {e}")
            time.sleep(3600)  # Refresh every hour

    def refresh_memory(self) -> int:
        """
        Rebuild market memory from pattern stats.
        Returns count of memory entries updated.
        """
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT * FROM hie_pattern_stats WHERE occurrences >= 10",
                conn
            )
            conn.close()
        except Exception as e:
            logger.error(f"Memory refresh read error: {e}")
            return 0

        if df.empty:
            return 0

        count = 0
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        now = dt.datetime.utcnow().isoformat()

        rows_to_insert = []
        for _, row in df.iterrows():
            win_rate = float(row["win_rate"])
            avg_rr = float(row["avg_rr"])
            occ = int(row["occurrences"])

            is_strong = 1 if win_rate >= 65 and avg_rr >= 1.5 else 0
            is_weak = 1 if win_rate < 45 else 0

            if is_strong:
                label = f"✅ STRONG: {win_rate:.0f}% WR | {avg_rr:.1f}R avg | {occ} trades"
            elif is_weak:
                label = f"⚠️ WEAK: {win_rate:.0f}% WR | {avg_rr:.1f}R avg | {occ} trades"
            else:
                label = f"📊 NEUTRAL: {win_rate:.0f}% WR | {avg_rr:.1f}R avg | {occ} trades"

            rows_to_insert.append((
                row["symbol"], row["setup_type"], row["session"], row["direction"],
                occ, win_rate, avg_rr, label, is_strong, is_weak, now
            ))

        count = 0
        if rows_to_insert:
            try:
                conn.executemany("""
                    INSERT OR REPLACE INTO hie_market_memory
                    (symbol, setup_type, session, direction, occurrences, win_rate, avg_rr,
                     memory_label, is_strong, is_weak, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, rows_to_insert)
                count = len(rows_to_insert)
                conn.commit()
            except Exception as e:
                logger.error(f"Memory refresh write error: {e}")
        conn.close()

        # Update in-memory cache
        self._rebuild_cache()
        logger.info(f"🧠 Market Memory refreshed: {count} entries.")
        return count

    def _rebuild_cache(self):
        """Rebuild fast in-memory lookup cache from DB."""
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            df = pd.read_sql_query("SELECT * FROM hie_market_memory", conn)
            conn.close()
            if not df.empty:
                self._memory_cache = {}
                for _, row in df.iterrows():
                    key = f"{row['symbol']}|{row['setup_type']}|{row['session']}|{row['direction']}"
                    self._memory_cache[key] = dict(row)
        except Exception:
            pass

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_memory(
        self,
        symbol: str,
        session: Optional[str] = None,
        setup_type: Optional[str] = None,
        direction: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Retrieve memory for a given symbol+session+setup+direction.
        Falls back to broader queries if exact match not found.
        """
        # Try exact match from cache first
        if session and setup_type and direction:
            key = f"{symbol}|{setup_type}|{session}|{direction}"
            if key in self._memory_cache:
                return self._memory_cache[key]

        # DB fallback
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            q = "SELECT * FROM hie_market_memory WHERE symbol=?"
            params = [symbol]
            if session:
                q += " AND session=?"; params.append(session)
            if setup_type:
                q += " AND setup_type=?"; params.append(setup_type)
            if direction:
                q += " AND direction=?"; params.append(direction)
            q += " ORDER BY occurrences DESC LIMIT 1"
            df = pd.read_sql_query(q, conn, params=params)
            conn.close()
            if not df.empty:
                return df.iloc[0].to_dict()
        except Exception as e:
            logger.error(f"Memory get error: {e}")
        return None

    def get_memory_score(self, symbol: str, session: str, setup_type: str, direction: str) -> float:
        """
        Return a normalized memory score 0-100 based on historical win rate and avg RR.
        Used to feed into the HIE scoring engine.
        """
        mem = self.get_memory(symbol, session, setup_type, direction)
        if not mem:
            return 50.0  # Neutral if no data

        win_rate = float(mem.get("win_rate", 50))
        avg_rr = float(mem.get("avg_rr", 1.0))
        occ = int(mem.get("occurrences", 0))

        # Weight by data confidence: low sample = regress toward neutral (50)
        confidence = min(1.0, occ / 50.0)
        raw_score = (win_rate * 0.6 + min(avg_rr * 20, 40))  # Win rate 0-60 pts + RR 0-40 pts
        blended = 50 + (raw_score - 50) * confidence
        return round(max(0, min(100, blended)), 2)

    def get_best_session(self, symbol: str, setup_type: Optional[str] = None) -> Optional[str]:
        """Return the session with the highest win rate for a given symbol."""
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            q = "SELECT session, AVG(win_rate) as avg_wr FROM hie_market_memory WHERE symbol=?"
            params = [symbol]
            if setup_type:
                q += " AND setup_type=?"; params.append(setup_type)
            q += " GROUP BY session ORDER BY avg_wr DESC LIMIT 1"
            cursor = conn.cursor()
            cursor.execute(q, params)
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            return None

    def get_symbol_memory_summary(self, symbol: str) -> Dict:
        """Return condensed memory summary for a symbol."""
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT * FROM hie_market_memory WHERE symbol=? ORDER BY win_rate DESC",
                conn, params=[symbol]
            )
            conn.close()
            if df.empty:
                return {"symbol": symbol, "no_data": True}

            strong = df[df["is_strong"] == 1].to_dict(orient="records")
            weak = df[df["is_weak"] == 1].to_dict(orient="records")
            best_session = df.groupby("session")["win_rate"].mean().idxmax() if "session" in df.columns else None

            return {
                "symbol": symbol,
                "total_memory_entries": len(df),
                "strong_setups": strong[:5],
                "weak_setups": weak[:5],
                "best_session": best_session,
                "overall_avg_wr": round(float(df["win_rate"].mean()), 2),
                "overall_avg_rr": round(float(df["avg_rr"].mean()), 2)
            }
        except Exception as e:
            logger.error(f"Symbol memory summary error: {e}")
            return {"symbol": symbol, "error": str(e)}

    def get_all_memory(self, limit: int = 200) -> List[Dict]:
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            df = pd.read_sql_query(
                f"SELECT * FROM hie_market_memory ORDER BY win_rate DESC LIMIT {limit}",
                conn
            )
            conn.close()
            return df.to_dict(orient="records") if not df.empty else []
        except Exception:
            return []


# Singleton
market_memory_engine = MarketMemoryEngine()
