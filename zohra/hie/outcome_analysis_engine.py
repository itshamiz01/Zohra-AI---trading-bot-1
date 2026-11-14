"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 4 — OUTCOME ANALYSIS ENGINE                                 ║
║   Measures R-multiple results for every detected historical setup.   ║
║   Stores win/loss, MFE, MAE, reached_0.5R through reached_5R.      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import time
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.outcome_analysis")


class OutcomeAnalysisEngine:
    """
    For every setup in hie_setups, forward-tests subsequent candles
    to determine how far price moved. Saves results to hie_setup_outcomes.
    """

    R_TARGETS = [0.5, 1.0, 2.0, 3.0, 5.0]

    def __init__(self):
        from zohra.hie.historical_data_engine import historical_data_engine
        self._hde = historical_data_engine
        self._db_path = historical_data_engine.db_path_hie
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_table()

    def _init_table(self):
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_setup_outcomes (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    setup_id     INTEGER NOT NULL UNIQUE,
                    symbol       TEXT NOT NULL,
                    timeframe    TEXT NOT NULL,
                    setup_type   TEXT NOT NULL,
                    direction    TEXT NOT NULL,
                    session      TEXT NOT NULL,
                    timestamp    TEXT NOT NULL,
                    entry_price  REAL NOT NULL,
                    stop_loss    REAL NOT NULL,
                    take_profit  REAL NOT NULL,
                    risk_r       REAL NOT NULL,
                    reached_0_5r INTEGER DEFAULT 0,
                    reached_1r   INTEGER DEFAULT 0,
                    reached_2r   INTEGER DEFAULT 0,
                    reached_3r   INTEGER DEFAULT 0,
                    reached_5r   INTEGER DEFAULT 0,
                    is_win       INTEGER DEFAULT 0,
                    pnl_r        REAL DEFAULT 0,
                    mfe_r        REAL DEFAULT 0,
                    mae_r        REAL DEFAULT 0,
                    bars_held    INTEGER DEFAULT 0,
                    FOREIGN KEY(setup_id) REFERENCES hie_setups(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome_sym ON hie_setup_outcomes(symbol, setup_type, session)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"OutcomeAnalysis init error: {e}")

    # ──────────────────────────────────────────────
    #  BACKGROUND ANALYSIS
    # ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-OutcomeAnalysis")
        self._thread.start()
        logger.info("📊 HIE Outcome Analysis Engine started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Process unanalyzed setups in batches."""
        while self._running:
            try:
                processed = self._process_unanalyzed_batch(batch_size=500)
                if processed == 0:
                    time.sleep(300)  # Sleep 5 min if nothing to process
                else:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"OutcomeAnalysis loop error: {e}")
                time.sleep(60)

    def _process_unanalyzed_batch(self, batch_size: int = 500) -> int:
        """Process a batch of setups that haven't been analyzed yet."""
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            df = pd.read_sql_query(
                f"SELECT * FROM hie_setups WHERE outcome_analyzed = 0 LIMIT {batch_size}",
                conn
            )
            if df.empty:
                return 0

            outcomes_to_store = []
            setups_to_mark = []

            for _, setup in df.iterrows():
                if not self._running:
                    break
                try:
                    outcome = self.analyze_outcome_for_setup(dict(setup), conn)
                    if outcome:
                        outcomes_to_store.append(outcome)
                    setups_to_mark.append((int(setup["id"]),))
                except Exception as e:
                    logger.debug(f"Outcome error for setup {setup.get('id')}: {e}")
                    setups_to_mark.append((int(setup["id"]),))  # Mark to avoid retrying

            if outcomes_to_store:
                outcome_rows = [(
                    o["setup_id"], o["symbol"], o["timeframe"], o["setup_type"],
                    o["direction"], o["session"], o["timestamp"], o["entry_price"],
                    o["stop_loss"], o["take_profit"], o["risk_r"], o["reached_0_5r"],
                    o["reached_1r"], o["reached_2r"], o["reached_3r"], o["reached_5r"],
                    o["is_win"], o["pnl_r"], o["mfe_r"], o["mae_r"], o["bars_held"]
                ) for o in outcomes_to_store]
                
                conn.executemany("""
                    INSERT OR REPLACE INTO hie_setup_outcomes
                    (setup_id, symbol, timeframe, setup_type, direction, session, timestamp,
                     entry_price, stop_loss, take_profit, risk_r,
                     reached_0_5r, reached_1r, reached_2r, reached_3r, reached_5r,
                     is_win, pnl_r, mfe_r, mae_r, bars_held)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, outcome_rows)

            if setups_to_mark:
                conn.executemany(
                    "UPDATE hie_setups SET outcome_analyzed=1 WHERE id=?",
                    setups_to_mark
                )

            if outcomes_to_store or setups_to_mark:
                conn.commit()

            return len(setups_to_mark)
        except Exception as e:
            logger.error(f"Batch processing error: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    def analyze_outcome_for_setup(self, setup: Dict, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict]:
        """
        Forward-measure candles after setup timestamp to determine outcome.
        Returns outcome dict or None if insufficient data.
        """
        symbol = setup["symbol"]
        tf = setup["timeframe"]
        setup_ts = setup["timestamp"]
        entry = float(setup["entry_price"])
        sl = float(setup["stop_loss"])
        tp = float(setup["take_profit"])
        direction = setup["direction"]

        risk_r = abs(entry - sl)
        if risk_r <= 0:
            return None

        # Get forward candles (up to 200 bars after setup)
        local_conn = False
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            local_conn = True
        try:
            fwd_df = pd.read_sql_query(
                "SELECT timestamp, high, low, close FROM hie_candles "
                "WHERE symbol=? AND timeframe=? AND timestamp > ? "
                "ORDER BY timestamp ASC LIMIT 200",
                conn, params=[symbol, tf, setup_ts]
            )
        except Exception:
            return None
        finally:
            if local_conn and conn:
                conn.close()

        if fwd_df.empty or len(fwd_df) < 3:
            return None

        # Forward-test price action
        mfe_r = 0.0   # Max Favorable Excursion in R-multiples
        mae_r = 0.0   # Max Adverse Excursion in R-multiples
        reached_r = {0.5: 0, 1.0: 0, 2.0: 0, 3.0: 0, 5.0: 0}
        is_win = 0
        final_pnl_r = 0.0
        bars_held = 0
        exit_found = False

        for bars_held, (_, candle) in enumerate(fwd_df.iterrows()):
            high = float(candle["high"])
            low = float(candle["low"])

            if direction == "LONG":
                favorable = (high - entry) / risk_r
                adverse = (entry - low) / risk_r
                # Check SL hit
                if low <= sl:
                    final_pnl_r = -1.0
                    is_win = 0
                    exit_found = True
                    break
                # Check TP hit
                if high >= tp:
                    final_pnl_r = abs(tp - entry) / risk_r
                    is_win = 1
                    exit_found = True
                    break
            else:  # SHORT
                favorable = (entry - low) / risk_r
                adverse = (high - entry) / risk_r
                if high >= sl:
                    final_pnl_r = -1.0
                    is_win = 0
                    exit_found = True
                    break
                if low <= tp:
                    final_pnl_r = abs(entry - tp) / risk_r
                    is_win = 1
                    exit_found = True
                    break

            mfe_r = max(mfe_r, favorable)
            mae_r = max(mae_r, adverse)

            # Track R-milestone hits
            for r_target in self.R_TARGETS:
                if favorable >= r_target:
                    reached_r[r_target] = 1

        if not exit_found:
            # Position still open at end of data — use last close
            last_close = float(fwd_df["close"].iloc[-1])
            if direction == "LONG":
                final_pnl_r = (last_close - entry) / risk_r
            else:
                final_pnl_r = (entry - last_close) / risk_r
            is_win = 1 if final_pnl_r > 0 else 0

        return {
            "setup_id": int(setup["id"]),
            "symbol": symbol,
            "timeframe": tf,
            "setup_type": setup["setup_type"],
            "direction": direction,
            "session": setup["session"],
            "timestamp": setup_ts,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "risk_r": round(risk_r, 6),
            "reached_0_5r": reached_r[0.5],
            "reached_1r": reached_r[1.0],
            "reached_2r": reached_r[2.0],
            "reached_3r": reached_r[3.0],
            "reached_5r": reached_r[5.0],
            "is_win": is_win,
            "pnl_r": round(final_pnl_r, 4),
            "mfe_r": round(mfe_r, 4),
            "mae_r": round(mae_r, 4),
            "bars_held": bars_held
        }

    def _store_outcome(self, outcome: Dict, conn: Optional[sqlite3.Connection] = None):
        local_conn = False
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            local_conn = True
        try:
            conn.execute("""
                INSERT OR REPLACE INTO hie_setup_outcomes
                (setup_id, symbol, timeframe, setup_type, direction, session, timestamp,
                 entry_price, stop_loss, take_profit, risk_r,
                 reached_0_5r, reached_1r, reached_2r, reached_3r, reached_5r,
                 is_win, pnl_r, mfe_r, mae_r, bars_held)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                outcome["setup_id"], outcome["symbol"], outcome["timeframe"],
                outcome["setup_type"], outcome["direction"], outcome["session"],
                outcome["timestamp"], outcome["entry_price"], outcome["stop_loss"],
                outcome["take_profit"], outcome["risk_r"],
                outcome["reached_0_5r"], outcome["reached_1r"], outcome["reached_2r"],
                outcome["reached_3r"], outcome["reached_5r"], outcome["is_win"],
                outcome["pnl_r"], outcome["mfe_r"], outcome["mae_r"], outcome["bars_held"]
            ))
            if local_conn:
                conn.commit()
        except Exception as e:
            logger.error(f"Outcome store error: {e}")
        finally:
            if local_conn and conn:
                conn.close()

    def _mark_analyzed(self, setup_id: int, conn: Optional[sqlite3.Connection] = None):
        local_conn = False
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            local_conn = True
        try:
            conn.execute("UPDATE hie_setups SET outcome_analyzed=1 WHERE id=?", (setup_id,))
            if local_conn:
                conn.commit()
        except Exception:
            pass
        finally:
            if local_conn and conn:
                conn.close()

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_outcomes(
        self,
        symbol: Optional[str] = None,
        setup_type: Optional[str] = None,
        session: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """Query stored outcomes with optional filters."""
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            q = "SELECT * FROM hie_setup_outcomes WHERE 1=1"
            params = []
            if symbol:
                q += " AND symbol=?"; params.append(symbol)
            if setup_type:
                q += " AND setup_type=?"; params.append(setup_type)
            if session:
                q += " AND session=?"; params.append(session)
            if direction:
                q += " AND direction=?"; params.append(direction)
            q += f" ORDER BY timestamp DESC LIMIT {int(limit)}"
            df = pd.read_sql_query(q, conn, params=params)
            return df.to_dict(orient="records") if not df.empty else []
        except Exception as e:
            logger.error(f"OutcomeAnalysis get_outcomes error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_outcome_count(self) -> int:
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM hie_setup_outcomes")
            n = cursor.fetchone()[0]
            return n
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()

    def get_pending_count(self) -> int:
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM hie_setups WHERE outcome_analyzed=0")
            n = cursor.fetchone()[0]
            return n
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()


# Singleton
outcome_analysis_engine = OutcomeAnalysisEngine()
