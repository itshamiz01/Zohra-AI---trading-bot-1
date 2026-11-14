"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 12 — CONFIDENCE CALIBRATION ENGINE                          ║
║   Verifies that Zohra's confidence scores predict outcomes correctly.║
║   Tracks: expected win rate per score bucket vs actual win rate.     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import time
import datetime as dt
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.calibration")

# Score buckets for calibration
SCORE_BUCKETS = [
    (60, 69, "60-69"),
    (70, 79, "70-79"),
    (80, 89, "80-89"),
    (90, 100, "90-100"),
]


class ConfidenceCalibrationEngine:
    """
    Measures how accurately Zohra's confidence scores predict trade outcomes.
    Compares expected win rate (from score) vs actual win rate from trade history.

    Example:
        Score 90-100 → Expected win rate: 90%+
        Actual win rate measured: 78%
        Calibration error: -12% (overconfident)
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
                CREATE TABLE IF NOT EXISTS hie_confidence_calibration (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    bucket_label     TEXT NOT NULL UNIQUE,
                    bucket_min       INTEGER NOT NULL,
                    bucket_max       INTEGER NOT NULL,
                    trade_count      INTEGER DEFAULT 0,
                    wins             INTEGER DEFAULT 0,
                    expected_win_pct REAL DEFAULT 0,
                    actual_win_pct   REAL DEFAULT 0,
                    calibration_err  REAL DEFAULT 0,
                    avg_pnl_usd      REAL DEFAULT 0,
                    calibration_grade TEXT,
                    updated_at       TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Calibration init error: {e}")

    # ──────────────────────────────────────────────
    #  BACKGROUND CALIBRATION
    # ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-Calibration")
        self._thread.start()
        logger.info("🎯 HIE Confidence Calibration Engine started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                self.calibrate()
            except Exception as e:
                logger.error(f"Calibration loop error: {e}")
            time.sleep(3600)  # Run every hour

    def calibrate(self) -> Dict:
        """
        Run calibration analysis against Bot A's closed trade history.
        Returns calibration report dict.
        """
        try:
            conn = sqlite3.connect(self._trade_db, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT confidence_score, pnl_usd FROM trades WHERE pnl_usd IS NOT NULL AND confidence_score IS NOT NULL",
                conn
            )
            conn.close()
        except Exception as e:
            logger.error(f"Calibration read error: {e}")
            return {"error": str(e), "buckets": []}

        if df.empty or len(df) < 5:
            return {"status": "insufficient_data", "trade_count": len(df), "buckets": []}

        df["is_win"] = (df["pnl_usd"] > 0).astype(int)
        report_buckets = []
        now = dt.datetime.utcnow().isoformat()

        conn_hie = sqlite3.connect(self._hie_db, timeout=30.0)
        conn_hie.execute("PRAGMA journal_mode=WAL")

        for bucket_min, bucket_max, label in SCORE_BUCKETS:
            bucket_df = df[(df["confidence_score"] >= bucket_min) & (df["confidence_score"] <= bucket_max)]
            n = len(bucket_df)
            wins = int(bucket_df["is_win"].sum()) if n > 0 else 0
            actual_wr = round(wins / n * 100, 2) if n > 0 else 0
            expected_wr = round((bucket_min + bucket_max) / 2, 1)
            cal_error = round(actual_wr - expected_wr, 2)
            avg_pnl = round(float(bucket_df["pnl_usd"].mean()), 2) if n > 0 else 0

            # Calibration grade
            abs_err = abs(cal_error)
            if abs_err <= 5:
                grade = "EXCELLENT"
            elif abs_err <= 10:
                grade = "GOOD"
            elif abs_err <= 20:
                grade = "FAIR"
            else:
                grade = "POOR"

            bucket_result = {
                "bucket": label,
                "bucket_min": bucket_min,
                "bucket_max": bucket_max,
                "trade_count": n,
                "wins": wins,
                "expected_win_pct": expected_wr,
                "actual_win_pct": actual_wr,
                "calibration_error": cal_error,
                "calibration_direction": "OVERCONFIDENT" if cal_error < -5 else "UNDERCONFIDENT" if cal_error > 5 else "WELL_CALIBRATED",
                "avg_pnl_usd": avg_pnl,
                "calibration_grade": grade
            }
            report_buckets.append(bucket_result)

            # Store to HIE DB
            try:
                conn_hie.execute("""
                    INSERT OR REPLACE INTO hie_confidence_calibration
                    (bucket_label, bucket_min, bucket_max, trade_count, wins,
                     expected_win_pct, actual_win_pct, calibration_err, avg_pnl_usd, calibration_grade, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (label, bucket_min, bucket_max, n, wins,
                      expected_wr, actual_wr, cal_error, avg_pnl, grade, now))
            except Exception:
                pass

        conn_hie.commit()
        conn_hie.close()

        overall = {
            "status": "success",
            "trade_count": len(df),
            "generated_at": now,
            "buckets": report_buckets,
            "summary": self._summarize(report_buckets)
        }

        logger.info(f"🎯 Calibration complete: {len(df)} trades analyzed across {len(report_buckets)} score buckets.")
        return overall

    def _summarize(self, buckets: List[Dict]) -> str:
        filled = [b for b in buckets if b["trade_count"] >= 5]
        if not filled:
            return "Insufficient trade data for calibration summary."

        overconf = [b for b in filled if b["calibration_direction"] == "OVERCONFIDENT"]
        underconf = [b for b in filled if b["calibration_direction"] == "UNDERCONFIDENT"]
        well_cal = [b for b in filled if b["calibration_direction"] == "WELL_CALIBRATED"]

        lines = []
        if overconf:
            lines.append(f"OVERCONFIDENT in {len(overconf)} buckets: {', '.join(b['bucket'] for b in overconf)}")
        if underconf:
            lines.append(f"UNDERCONFIDENT in {len(underconf)} buckets: {', '.join(b['bucket'] for b in underconf)}")
        if well_cal:
            lines.append(f"WELL CALIBRATED in {len(well_cal)} buckets: {', '.join(b['bucket'] for b in well_cal)}")
        return " | ".join(lines) if lines else "Calibration analysis complete."

    # ──────────────────────────────────────────────
    #  QUERY API
    # ──────────────────────────────────────────────

    def get_calibration_report(self) -> Dict:
        """Return the latest stored calibration report."""
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT * FROM hie_confidence_calibration ORDER BY bucket_min ASC",
                conn
            )
            conn.close()
            if df.empty:
                return {"status": "no_data", "buckets": []}
            return {
                "status": "success",
                "buckets": df.to_dict(orient="records"),
                "total_buckets": len(df),
                "last_updated": df["updated_at"].max() if "updated_at" in df.columns else None
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "buckets": []}

    def get_score_adjustment(self, score: float) -> float:
        """
        Suggest score adjustment based on calibration data.
        If Zohra is overconfident in the 80-89 range, suggested adjusted score is lower.
        Returns the adjusted score suggestion (does NOT modify scoring — advisory only).
        """
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT calibration_err FROM hie_confidence_calibration WHERE bucket_min <= ? AND bucket_max >= ?",
                (int(score), int(score))
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                cal_err = float(row[0])
                # Suggest correction: if overconfident (err < 0), nudge score down
                adjusted = score + (cal_err * 0.3)  # Apply 30% of calibration error
                return round(max(0, min(100, adjusted)), 2)
        except Exception:
            pass
        return score  # No adjustment available


# Singleton
confidence_calibration_engine = ConfidenceCalibrationEngine()
