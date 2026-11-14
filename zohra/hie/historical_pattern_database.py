"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 5 — HISTORICAL PATTERN DATABASE                             ║
║   Aggregates setup outcomes into statistical pattern statistics.     ║
║   Builds the core memory: symbol × setup × session → win_rate, RR  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import time
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.pattern_db")


class HistoricalPatternDatabase:
    """
    Aggregates hie_setup_outcomes into hie_pattern_stats.
    Provides fast statistical lookup for any symbol+setup+session combination.
    """

    def __init__(self):
        from zohra.hie.historical_data_engine import historical_data_engine
        self._db_path = historical_data_engine.db_path_hie
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_table()

    def _init_table(self):
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_pattern_stats (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol       TEXT NOT NULL,
                    setup_type   TEXT NOT NULL,
                    direction    TEXT NOT NULL,
                    session      TEXT NOT NULL,
                    timeframe    TEXT NOT NULL,
                    occurrences  INTEGER DEFAULT 0,
                    wins         INTEGER DEFAULT 0,
                    losses       INTEGER DEFAULT 0,
                    win_rate     REAL DEFAULT 0,
                    avg_rr       REAL DEFAULT 0,
                    avg_mfe_r    REAL DEFAULT 0,
                    avg_mae_r    REAL DEFAULT 0,
                    reach_1r_pct REAL DEFAULT 0,
                    reach_2r_pct REAL DEFAULT 0,
                    reach_3r_pct REAL DEFAULT 0,
                    updated_at   TEXT NOT NULL,
                    UNIQUE(symbol, setup_type, direction, session, timeframe)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hie_pstats_sym ON hie_pattern_stats(symbol, setup_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hie_pstats_sess ON hie_pattern_stats(session)")
            conn.commit()
        except Exception as e:
            logger.error(f"PatternDB init error: {e}")
        finally:
            if conn:
                conn.close()

    # ──────────────────────────────────────────────
    #  BACKGROUND AGGREGATION
    # ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-PatternDB")
        self._thread.start()
        logger.info("📚 HIE Pattern Database Engine started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Rebuild pattern stats every 30 minutes."""
        while self._running:
            try:
                self.rebuild_stats()
            except Exception as e:
                logger.error(f"PatternDB rebuild error: {e}")
            time.sleep(1800)  # 30 minutes

    def rebuild_stats(self) -> int:
        """
        Rebuild hie_pattern_stats from hie_setup_outcomes.
        Returns number of pattern rows upserted.
        """
        df = pd.DataFrame()
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=60.0)
            df = pd.read_sql_query("SELECT * FROM hie_setup_outcomes", conn)
        except Exception as e:
            logger.error(f"PatternDB read error: {e}")
            return 0
        finally:
            if conn:
                conn.close()

        if df.empty:
            return 0

        # Aggregate by symbol × setup_type × direction × session × timeframe
        groups = df.groupby(["symbol", "setup_type", "direction", "session", "timeframe"])
        rows_upserted = 0

        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=60.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            rows_to_upsert = []
            for (symbol, setup_type, direction, session, timeframe), grp in groups:
                n = len(grp)
                wins = int(grp["is_win"].sum())
                losses = n - wins
                win_rate = round(wins / n * 100, 2) if n > 0 else 0
                avg_rr = round(float(grp["pnl_r"].mean()), 4)
                avg_mfe = round(float(grp["mfe_r"].mean()), 4)
                avg_mae = round(float(grp["mae_r"].mean()), 4)
                reach_1r = round(float(grp["reached_1r"].mean()) * 100, 2)
                reach_2r = round(float(grp["reached_2r"].mean()) * 100, 2)
                reach_3r = round(float(grp["reached_3r"].mean()) * 100, 2)
                import datetime as dt_mod
                now = dt_mod.datetime.utcnow().isoformat()

                rows_to_upsert.append((
                    symbol, setup_type, direction, session, timeframe,
                    n, wins, losses, win_rate, avg_rr,
                    avg_mfe, avg_mae, reach_1r, reach_2r, reach_3r, now
                ))

            if rows_to_upsert:
                conn.executemany("""
                    INSERT OR REPLACE INTO hie_pattern_stats
                    (symbol, setup_type, direction, session, timeframe,
                     occurrences, wins, losses, win_rate, avg_rr,
                     avg_mfe_r, avg_mae_r, reach_1r_pct, reach_2r_pct, reach_3r_pct, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, rows_to_upsert)
                rows_upserted = len(rows_to_upsert)

            conn.commit()
        except Exception as e:
            logger.error(f"PatternDB commit error: {e}")
        finally:
            if conn:
                conn.close()

        logger.info(f"✅ HIE PatternDB rebuilt: {rows_upserted} pattern rows updated.")
        return rows_upserted

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_pattern_stats(
        self,
        symbol: Optional[str] = None,
        setup_type: Optional[str] = None,
        session: Optional[str] = None,
        direction: Optional[str] = None,
        timeframe: Optional[str] = None,
        min_occurrences: int = 5,
        limit: int = 200
    ) -> List[Dict]:
        """Query pattern statistics with optional filters."""
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            q = "SELECT * FROM hie_pattern_stats WHERE occurrences >= ?"
            params = [min_occurrences]
            if symbol:
                q += " AND symbol=?"; params.append(symbol)
            if setup_type:
                q += " AND setup_type=?"; params.append(setup_type)
            if session:
                q += " AND session=?"; params.append(session)
            if direction:
                q += " AND direction=?"; params.append(direction)
            if timeframe:
                q += " AND timeframe=?"; params.append(timeframe)
            q += " ORDER BY win_rate DESC, occurrences DESC"
            q += f" LIMIT {int(limit)}"
            df = pd.read_sql_query(q, conn, params=params)
            return df.to_dict(orient="records") if not df.empty else []
        except Exception as e:
            logger.error(f"PatternDB get_stats error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_best_setup_for_symbol(self, symbol: str, session: Optional[str] = None) -> Optional[Dict]:
        """Return the highest win-rate setup for a given symbol."""
        results = self.get_pattern_stats(symbol=symbol, session=session, min_occurrences=10, limit=1)
        return results[0] if results else None

    def get_win_rate(
        self, symbol: str, setup_type: str, session: str, direction: str, timeframe: str = "H1"
    ) -> Optional[float]:
        """Return win rate for an exact combination, or None if insufficient data."""
        results = self.get_pattern_stats(
            symbol=symbol, setup_type=setup_type, session=session,
            direction=direction, timeframe=timeframe, min_occurrences=5, limit=1
        )
        if results:
            return results[0].get("win_rate")
        return None

    def get_avg_rr(
        self, symbol: str, setup_type: str, session: str, direction: str, timeframe: str = "H1"
    ) -> Optional[float]:
        results = self.get_pattern_stats(
            symbol=symbol, setup_type=setup_type, session=session,
            direction=direction, timeframe=timeframe, min_occurrences=5, limit=1
        )
        if results:
            return results[0].get("avg_rr")
        return None

    def get_top_patterns(self, limit: int = 20) -> List[Dict]:
        """Return top-performing patterns across all symbols."""
        return self.get_pattern_stats(min_occurrences=10, limit=limit)

    def get_worst_patterns(self, limit: int = 20) -> List[Dict]:
        """Return lowest win-rate patterns with sufficient data."""
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            df = pd.read_sql_query(
                f"SELECT * FROM hie_pattern_stats WHERE occurrences >= 10 ORDER BY win_rate ASC LIMIT {limit}",
                conn
            )
            return df.to_dict(orient="records") if not df.empty else []
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

    def get_stats_count(self) -> int:
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM hie_pattern_stats")
            n = cursor.fetchone()[0]
            return n
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()


# Singleton
historical_pattern_database = HistoricalPatternDatabase()
