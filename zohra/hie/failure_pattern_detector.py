"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 11 — FAILURE PATTERN DETECTOR                               ║
║   Scans historical outcomes for recurring losing patterns.           ║
║   Flags them automatically for Zohra's awareness.                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import time
import datetime as dt
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.failure_detector")

# Thresholds for flagging failure patterns
MIN_OCCURRENCES = 5
MIN_FAIL_RATE = 0.55  # 55% failure rate to flag


class FailurePatternDetector:
    """
    Detects and tracks recurring losing patterns from HIE outcome data.
    Stores results in the existing failure_patterns table in the trade DB
    AND in hie_failure_flags in the HIE DB.
    """

    def __init__(self):
        from zohra.hie.historical_data_engine import historical_data_engine
        self._hie_db = historical_data_engine.db_path_hie
        try:
            from zohra.config.settings import settings
            self._trade_db = settings.DB_PATH
        except Exception:
            self._trade_db = "logs/zohra_trades.db"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_table()

    def _init_table(self):
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_failure_flags (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol       TEXT NOT NULL,
                    setup_type   TEXT NOT NULL,
                    direction    TEXT NOT NULL,
                    session      TEXT NOT NULL,
                    timeframe    TEXT NOT NULL,
                    occurrences  INTEGER NOT NULL,
                    fail_rate    REAL NOT NULL,
                    avg_loss_r   REAL NOT NULL,
                    flag_reason  TEXT NOT NULL,
                    is_active    INTEGER DEFAULT 1,
                    detected_at  TEXT NOT NULL,
                    UNIQUE(symbol, setup_type, direction, session, timeframe)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hie_fail_sym ON hie_failure_flags(symbol, session)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"FailureDetector init error: {e}")

    # ──────────────────────────────────────────────
    #  BACKGROUND DETECTION
    # ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-FailureDetect")
        self._thread.start()
        logger.info("🚨 HIE Failure Pattern Detector started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                self.scan_and_flag()
            except Exception as e:
                logger.error(f"FailureDetector loop error: {e}")
            time.sleep(3600)  # Scan every hour

    def scan_and_flag(self) -> int:
        """
        Scan pattern stats for recurring failures and flag them.
        Returns count of new patterns flagged.
        """
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            df = pd.read_sql_query(
                f"SELECT * FROM hie_pattern_stats WHERE occurrences >= {MIN_OCCURRENCES}",
                conn
            )
            conn.close()
        except Exception as e:
            logger.error(f"FailureDetector read error: {e}")
            return 0

        if df.empty:
            return 0

        # Identify failure patterns: high loss rate
        df["fail_rate"] = (100 - df["win_rate"]) / 100
        failures = df[df["fail_rate"] >= MIN_FAIL_RATE].copy()

        count = 0
        now = dt.datetime.utcnow().isoformat()
        conn = sqlite3.connect(self._hie_db, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")

        for _, row in failures.iterrows():
            fail_rate = float(row["fail_rate"])
            occ = int(row["occurrences"])
            avg_loss = abs(float(row.get("avg_rr", 0)))  # Negative RR indicates loss

            reason = (
                f"{occ} occurrences detected | "
                f"Fail rate: {fail_rate*100:.0f}% | "
                f"Avg loss: {avg_loss:.2f}R | "
                f"Session: {row['session']}"
            )

            try:
                conn.execute("""
                    INSERT OR REPLACE INTO hie_failure_flags
                    (symbol, setup_type, direction, session, timeframe, occurrences, fail_rate, avg_loss_r, flag_reason, is_active, detected_at)
                    VALUES (?,?,?,?,?,?,?,?,?,1,?)
                """, (
                    row["symbol"], row["setup_type"], row["direction"],
                    row["session"], row["timeframe"],
                    occ, fail_rate * 100, avg_loss, reason, now
                ))
                count += 1
            except Exception:
                pass

        conn.commit()
        conn.close()

        # Also sync to trade DB failure_patterns table
        self._sync_to_trade_db(failures)

        if count > 0:
            logger.warning(f"🚨 Failure Detector: {count} recurring failure patterns flagged.")
        return count

    def _sync_to_trade_db(self, failures: pd.DataFrame):
        """Sync failure patterns to existing trade DB failure_patterns table."""
        try:
            import json
            conn = sqlite3.connect(self._trade_db, timeout=30.0)
            cursor = conn.cursor()
            for _, row in failures.iterrows():
                sig = f"{row['symbol']}+{row['setup_type']}+{row['session']}+{row['direction']}"
                confl = json.dumps([row["symbol"], row["setup_type"], row["session"], row["direction"]])
                fail_rate = float((100 - row["win_rate"]) / 100 * 100)
                avg_loss = abs(float(row.get("avg_rr", 0)))
                cursor.execute("""
                    INSERT OR REPLACE INTO failure_patterns
                    (failure_signature, confluences, occurrences, fail_rate, avg_loss)
                    VALUES (?,?,?,?,?)
                """, (sig, confl, int(row["occurrences"]), fail_rate, avg_loss))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Sync to trade DB error: {e}")

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_flagged_patterns(
        self,
        symbol: Optional[str] = None,
        session: Optional[str] = None,
        active_only: bool = True,
        limit: int = 50
    ) -> List[Dict]:
        """Return flagged failure patterns."""
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            q = "SELECT * FROM hie_failure_flags WHERE 1=1"
            params = []
            if active_only:
                q += " AND is_active=1"
            if symbol:
                q += " AND symbol=?"; params.append(symbol)
            if session:
                q += " AND session=?"; params.append(session)
            q += f" ORDER BY fail_rate DESC, occurrences DESC LIMIT {int(limit)}"
            df = pd.read_sql_query(q, conn, params=params)
            conn.close()
            return df.to_dict(orient="records") if not df.empty else []
        except Exception as e:
            logger.error(f"GetFlagged error: {e}")
            return []

    def is_flagged(self, symbol: str, setup_type: str, session: str, direction: str) -> Optional[Dict]:
        """Check if a specific setup is flagged as a recurring failure."""
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM hie_failure_flags WHERE symbol=? AND setup_type=? AND session=? AND direction=? AND is_active=1",
                (symbol, setup_type, session, direction)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                cols = [d[0] for d in cursor.description] if cursor.description else []
                return dict(zip(cols, row)) if cols else {"flagged": True}
            return None
        except Exception:
            return None

    def get_flagged_count(self) -> int:
        try:
            conn = sqlite3.connect(self._hie_db, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM hie_failure_flags WHERE is_active=1")
            n = cursor.fetchone()[0]
            conn.close()
            return n
        except Exception:
            return 0


# Singleton
failure_pattern_detector = FailurePatternDetector()
