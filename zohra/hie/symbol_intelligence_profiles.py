"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 7 — SYMBOL INTELLIGENCE PROFILES                            ║
║   Generates per-symbol intelligence profiles:                        ║
║   best session, worst session, best setup, worst setup, WR, RR.     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import time
import datetime as dt
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.symbol_profiles")


class SymbolIntelligenceProfiles:
    """
    Generates and serves per-symbol intelligence profiles.
    Each profile includes statistically validated best/worst conditions.
    """

    def __init__(self):
        from zohra.hie.historical_data_engine import historical_data_engine
        self._db_path = historical_data_engine.db_path_hie
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._profiles_cache: Dict[str, Dict] = {}
        self._init_table()

    def _init_table(self):
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_symbol_profiles (
                    symbol           TEXT PRIMARY KEY,
                    best_session     TEXT,
                    worst_session    TEXT,
                    best_timeframe   TEXT,
                    worst_timeframe  TEXT,
                    best_setup       TEXT,
                    worst_setup      TEXT,
                    best_direction   TEXT,
                    overall_win_rate REAL DEFAULT 0,
                    overall_avg_rr   REAL DEFAULT 0,
                    total_setups     INTEGER DEFAULT 0,
                    profile_json     TEXT DEFAULT '{}',
                    updated_at       TEXT NOT NULL
                )
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"SymbolProfiles init error: {e}")
        finally:
            if conn:
                conn.close()

    # ──────────────────────────────────────────────
    #  BACKGROUND REFRESH
    # ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-SymbolProfiles")
        self._thread.start()
        logger.info("🏆 HIE Symbol Intelligence Profiles started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                self.rebuild_all_profiles()
            except Exception as e:
                logger.error(f"SymbolProfiles rebuild error: {e}")
            time.sleep(7200)  # Rebuild every 2 hours

    def rebuild_all_profiles(self) -> int:
        """Build profiles for all symbols with data in pattern stats."""
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            symbols = pd.read_sql_query(
                "SELECT DISTINCT symbol FROM hie_pattern_stats WHERE occurrences >= 5",
                conn
            )["symbol"].tolist()
        except Exception as e:
            logger.error(f"SymbolProfiles rebuild error fetching symbols: {e}")
            return 0
        finally:
            if conn:
                conn.close()

        count = 0
        for symbol in symbols:
            if not self._running:
                break
            try:
                # Use a clean, isolated connection per symbol profile build/store to avoid long-lived locks
                with sqlite3.connect(self._db_path, timeout=30.0) as symbol_conn:
                    symbol_conn.execute("PRAGMA journal_mode=WAL")
                    symbol_conn.execute("PRAGMA synchronous=NORMAL")
                    symbol_conn.execute("BEGIN IMMEDIATE")
                    profile = self._build_profile(symbol, symbol_conn)
                    if profile:
                        self._store_profile(symbol, profile, symbol_conn)
                        self._profiles_cache[symbol] = profile
                        symbol_conn.commit()
                        count += 1
            except Exception as e:
                logger.debug(f"Profile build error {symbol}: {e}")
            time.sleep(0.05)  # yield to allow other threads to write

        return count

    def _build_profile(self, symbol: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict]:
        """Build intelligence profile for a single symbol."""
        local_conn = False
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            local_conn = True
        try:
            df = pd.read_sql_query(
                "SELECT * FROM hie_pattern_stats WHERE symbol=? AND occurrences >= 5",
                conn, params=[symbol]
            )
        except Exception:
            return None
        finally:
            if local_conn and conn:
                conn.close()

        if df.empty:
            return None

        import json

        def best_by(col: str, group_by: str, ascending=False) -> Optional[str]:
            try:
                agg = df.groupby(group_by)[col].mean()
                return str(agg.idxmax() if not ascending else agg.idxmin())
            except Exception:
                return None

        best_session = best_by("win_rate", "session")
        worst_session = best_by("win_rate", "session", ascending=True)
        best_tf = best_by("win_rate", "timeframe")
        worst_tf = best_by("win_rate", "timeframe", ascending=True)
        best_setup = best_by("win_rate", "setup_type")
        worst_setup = best_by("win_rate", "setup_type", ascending=True)
        best_dir = best_by("win_rate", "direction")

        overall_wr = round(float(df["win_rate"].mean()), 2)
        overall_rr = round(float(df["avg_rr"].mean()), 4)
        total_setups = int(df["occurrences"].sum())

        # Detailed breakdown by session
        session_breakdown = {}
        for sess, grp in df.groupby("session"):
            session_breakdown[sess] = {
                "win_rate": round(float(grp["win_rate"].mean()), 2),
                "avg_rr": round(float(grp["avg_rr"].mean()), 4),
                "occurrences": int(grp["occurrences"].sum())
            }

        # Detailed breakdown by setup type
        setup_breakdown = {}
        for st, grp in df.groupby("setup_type"):
            setup_breakdown[st] = {
                "win_rate": round(float(grp["win_rate"].mean()), 2),
                "avg_rr": round(float(grp["avg_rr"].mean()), 4),
                "occurrences": int(grp["occurrences"].sum())
            }

        profile = {
            "symbol": symbol,
            "best_session": best_session,
            "worst_session": worst_session,
            "best_timeframe": best_tf,
            "worst_timeframe": worst_tf,
            "best_setup": best_setup,
            "worst_setup": worst_setup,
            "best_direction": best_dir,
            "overall_win_rate": overall_wr,
            "overall_avg_rr": overall_rr,
            "total_setups": total_setups,
            "session_breakdown": session_breakdown,
            "setup_breakdown": setup_breakdown,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        return profile

    def _store_profile(self, symbol: str, profile: Dict, conn: Optional[sqlite3.Connection] = None):
        import json
        local_conn = False
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            local_conn = True
        try:
            conn.execute("""
                INSERT OR REPLACE INTO hie_symbol_profiles
                (symbol, best_session, worst_session, best_timeframe, worst_timeframe,
                 best_setup, worst_setup, best_direction, overall_win_rate, overall_avg_rr,
                 total_setups, profile_json, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                symbol,
                profile.get("best_session"), profile.get("worst_session"),
                profile.get("best_timeframe"), profile.get("worst_timeframe"),
                profile.get("best_setup"), profile.get("worst_setup"),
                profile.get("best_direction"),
                profile.get("overall_win_rate", 0),
                profile.get("overall_avg_rr", 0),
                profile.get("total_setups", 0),
                json.dumps(profile),
                profile.get("updated_at", dt.datetime.utcnow().isoformat())
            ))
            if local_conn:
                conn.commit()
        except Exception as e:
            logger.error(f"Profile store error: {e}")
        finally:
            if local_conn and conn:
                conn.close()

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_profile(self, symbol: str) -> Optional[Dict]:
        """Return intelligence profile for a symbol (cache-first, DB-fallback)."""
        if symbol in self._profiles_cache:
            return self._profiles_cache[symbol]
        conn = None
        try:
            import json
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("SELECT profile_json FROM hie_symbol_profiles WHERE symbol=?", (symbol,))
            row = cursor.fetchone()
            if row and row[0]:
                profile = json.loads(row[0])
                self._profiles_cache[symbol] = profile
                return profile
        except Exception as e:
            logger.error(f"Get profile error {symbol}: {e}")
        finally:
            if conn:
                conn.close()
        return None

    def get_symbol_score(self, symbol: str, session: str, setup_type: str, direction: str) -> float:
        """
        Return a 0-100 symbol intelligence score for a given trade context.
        """
        profile = self.get_profile(symbol)
        if not profile:
            return 50.0  # Neutral if no data

        score = 50.0  # Base neutral score

        # Reward if current session matches best session
        best_session = profile.get("best_session")
        worst_session = profile.get("worst_session")
        if best_session and session == best_session:
            score += 15.0
        elif worst_session and session == worst_session:
            score -= 15.0

        # Reward if current setup matches best setup
        best_setup = profile.get("best_setup")
        worst_setup = profile.get("worst_setup")
        if best_setup and setup_type == best_setup:
            score += 10.0
        elif worst_setup and setup_type == worst_setup:
            score -= 10.0

        # Reward if direction matches best direction
        best_dir = profile.get("best_direction")
        if best_dir and direction == best_dir:
            score += 5.0

        # Adjust by overall win rate
        overall_wr = profile.get("overall_win_rate", 50)
        score += (overall_wr - 50) * 0.4

        return round(max(0, min(100, score)), 2)

    def get_all_profiles(self) -> List[Dict]:
        """Return all stored symbol profiles."""
        conn = None
        try:
            import json
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT symbol, best_session, worst_session, best_setup, worst_setup, "
                "best_direction, overall_win_rate, overall_avg_rr, total_setups, updated_at "
                "FROM hie_symbol_profiles ORDER BY overall_win_rate DESC",
                conn
            )
            return df.to_dict(orient="records") if not df.empty else []
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

    def get_profiles_count(self) -> int:
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM hie_symbol_profiles")
            n = cursor.fetchone()[0]
            return n
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()


# Singleton
symbol_intelligence_profiles = SymbolIntelligenceProfiles()
