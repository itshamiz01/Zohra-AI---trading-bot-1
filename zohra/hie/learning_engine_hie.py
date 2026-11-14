"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 10 — LEARNING ENGINE HIE                                    ║
║   Extended learning analysis (does NOT replace pattern_detector.py) ║
║   Generates daily, weekly, monthly insights from HIE data.           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import time
import datetime as dt
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.learning")


class LearningEngineHIE:
    """
    Extended learning engine that generates insights from HIE pattern data.
    Works alongside (NOT replacing) the existing learning/pattern_detector.py.

    Generates:
      - Daily analysis: What worked today, what didn't
      - Weekly analysis: Best/worst patterns this week
      - Monthly analysis: Trend identification and parameter recommendations
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
        self._last_daily = None
        self._last_weekly = None
        self._last_monthly = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-Learning")
        self._thread.start()
        logger.info("📖 HIE Learning Engine started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Run analysis on schedule."""
        while self._running:
            try:
                now = dt.datetime.utcnow()

                # Daily: run at 22:00 UTC
                if now.hour == 22 and (self._last_daily is None or self._last_daily.date() < now.date()):
                    self.run_daily_analysis()
                    self._last_daily = now

                # Weekly: run on Sunday at 22:30 UTC
                if now.weekday() == 6 and now.hour == 22 and now.minute >= 30:
                    if self._last_weekly is None or (now - self._last_weekly).days >= 6:
                        self.run_weekly_analysis()
                        self._last_weekly = now

                # Monthly: run on 1st at 23:00 UTC
                if now.day == 1 and now.hour == 23:
                    if self._last_monthly is None or (now - self._last_monthly).days >= 28:
                        self.run_monthly_analysis()
                        self._last_monthly = now

            except Exception as e:
                logger.error(f"HIE learning loop error: {e}")
            time.sleep(1800)  # Check every 30 minutes

    # ──────────────────────────────────────────────
    #  ANALYSIS METHODS
    # ──────────────────────────────────────────────

    def run_daily_analysis(self) -> Dict:
        """Generate daily learning report from pattern stats."""
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            # Get patterns updated in last 24 hours
            since = (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat()
            df = pd.read_sql_query(
                "SELECT * FROM hie_pattern_stats WHERE updated_at >= ? ORDER BY win_rate DESC",
                conn, params=[since]
            )
            conn.close()

            insights = self._generate_insights(df, "DAILY")
            recs = self._generate_recommendations(df, "DAILY")
            self._store_recommendations(recs)

            return {
                "period": "daily",
                "generated_at": dt.datetime.utcnow().isoformat(),
                "patterns_analyzed": len(df),
                "insights": insights,
                "recommendations": recs
            }
        except Exception as e:
            logger.error(f"Daily analysis error: {e}")
            return {"period": "daily", "error": str(e), "insights": [], "recommendations": []}

    def run_weekly_analysis(self) -> Dict:
        """Generate weekly learning summary."""
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT * FROM hie_pattern_stats WHERE occurrences >= 5 ORDER BY win_rate DESC",
                conn
            )
            conn.close()

            insights = self._generate_insights(df, "WEEKLY")
            recs = self._generate_recommendations(df, "WEEKLY")
            self._store_recommendations(recs)

            # Also analyze trade history from trade DB
            trade_insights = self._analyze_recent_trades(days=7)

            return {
                "period": "weekly",
                "generated_at": dt.datetime.utcnow().isoformat(),
                "patterns_analyzed": len(df),
                "insights": insights + trade_insights,
                "recommendations": recs
            }
        except Exception as e:
            logger.error(f"Weekly analysis error: {e}")
            return {"period": "weekly", "error": str(e), "insights": [], "recommendations": []}

    def run_monthly_analysis(self) -> Dict:
        """Generate monthly analysis with full recommendations."""
        try:
            conn = sqlite3.connect(self._hie_db, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT * FROM hie_pattern_stats WHERE occurrences >= 10 ORDER BY win_rate DESC",
                conn
            )
            conn.close()

            insights = self._generate_insights(df, "MONTHLY")
            recs = self._generate_recommendations(df, "MONTHLY")
            self._store_recommendations(recs)
            trade_insights = self._analyze_recent_trades(days=30)

            return {
                "period": "monthly",
                "generated_at": dt.datetime.utcnow().isoformat(),
                "patterns_analyzed": len(df),
                "insights": insights + trade_insights,
                "recommendations": recs
            }
        except Exception as e:
            logger.error(f"Monthly analysis error: {e}")
            return {"period": "monthly", "error": str(e), "insights": [], "recommendations": []}

    def _generate_insights(self, df: pd.DataFrame, period: str) -> List[str]:
        """Generate human-readable insights from pattern data."""
        if df.empty:
            return [f"Insufficient historical data for {period.lower()} analysis. HIE backfill still in progress."]

        insights = []

        # Best performing symbol
        if "symbol" in df.columns:
            sym_perf = df.groupby("symbol")["win_rate"].mean()
            if not sym_perf.empty:
                best_sym = sym_perf.idxmax()
                best_wr = sym_perf.max()
                insights.append(f"🏆 Best performing symbol: {best_sym} ({best_wr:.1f}% historical win rate)")

                worst_sym = sym_perf.idxmin()
                worst_wr = sym_perf.min()
                insights.append(f"⚠️ Weakest performing symbol: {worst_sym} ({worst_wr:.1f}% historical win rate)")

        # Best session
        if "session" in df.columns:
            sess_perf = df.groupby("session")["win_rate"].mean()
            if not sess_perf.empty:
                best_sess = sess_perf.idxmax()
                best_sess_wr = sess_perf.max()
                insights.append(f"⏰ Best session: {best_sess} ({best_sess_wr:.1f}% avg win rate)")

        # Best setup type
        if "setup_type" in df.columns:
            setup_perf = df.groupby("setup_type")["win_rate"].mean()
            if not setup_perf.empty:
                best_setup = setup_perf.idxmax()
                best_setup_wr = setup_perf.max()
                insights.append(f"🎯 Most reliable setup: {best_setup} ({best_setup_wr:.1f}% win rate)")

                worst_setup = setup_perf.idxmin()
                worst_setup_wr = setup_perf.min()
                if worst_setup_wr < 45:
                    insights.append(f"🚫 Avoid: {worst_setup} setup only {worst_setup_wr:.1f}% win rate historically")

        # Highest avg RR
        if "avg_rr" in df.columns:
            high_rr = df.nlargest(1, "avg_rr")
            if not high_rr.empty:
                row = high_rr.iloc[0]
                insights.append(
                    f"💰 Best R:R setup: {row['setup_type']} on {row['symbol']} "
                    f"({row['session']}) — {row['avg_rr']:.1f}R avg"
                )

        return insights

    def _generate_recommendations(self, df: pd.DataFrame, period: str) -> List[Dict]:
        """Generate actionable trading recommendations."""
        if df.empty:
            return []

        recs = []

        if "symbol" in df.columns:
            sym_perf = df.groupby("symbol").agg(
                win_rate=("win_rate", "mean"),
                avg_rr=("avg_rr", "mean"),
                occ=("occurrences", "sum")
            ).reset_index()

            for _, row in sym_perf.iterrows():
                sym = row["symbol"]
                wr = row["win_rate"]
                occ = row["occ"]
                rr = row["avg_rr"]
                if occ < 10:
                    continue
                if wr >= 68 and rr >= 1.5:
                    recs.append({
                        "category": "PRIORITY",
                        "text": f"Increase {sym} allocation — {wr:.1f}% historical WR, {rr:.1f}R avg over {occ} setups.",
                        "evidence": f"{sym}: {occ} historical setups analyzed"
                    })
                elif wr <= 42:
                    recs.append({
                        "category": "REDUCE",
                        "text": f"Reduce {sym} exposure — only {wr:.1f}% historical WR over {occ} setups.",
                        "evidence": f"{sym}: {occ} setups, {wr:.1f}% WR"
                    })

        if "session" in df.columns:
            sess_perf = df.groupby("session").agg(win_rate=("win_rate", "mean"), occ=("occurrences", "sum")).reset_index()
            for _, row in sess_perf.iterrows():
                sess = row["session"]
                wr = row["win_rate"]
                occ = row["occ"]
                if occ < 10:
                    continue
                if wr <= 42:
                    recs.append({
                        "category": "FILTER",
                        "text": f"Filter {sess} session trades — {wr:.1f}% WR historically. Consider raising score threshold.",
                        "evidence": f"{sess}: {occ} historical trades, {wr:.1f}% WR"
                    })

        return recs

    def _analyze_recent_trades(self, days: int = 7) -> List[str]:
        """Analyze Bot A's recent live trade history for insights."""
        insights = []
        try:
            conn = sqlite3.connect(self._trade_db, timeout=30.0)
            since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
            df = pd.read_sql_query(
                "SELECT symbol, direction, session, pnl_usd, quality_grade, strategy_used "
                "FROM trades WHERE timestamp_close >= ? AND pnl_usd IS NOT NULL",
                conn, params=[since]
            )
            conn.close()

            if df.empty or len(df) < 3:
                return [f"Insufficient live trade data for {days}-day analysis."]

            df["is_win"] = (df["pnl_usd"] > 0).astype(int)
            total = len(df)
            wins = df["is_win"].sum()
            wr = wins / total * 100
            insights.append(f"📈 Live trades last {days}d: {total} trades, {wr:.1f}% win rate, ${df['pnl_usd'].sum():.2f} P&L")

        except Exception as e:
            logger.debug(f"Trade analysis error: {e}")
        return insights

    def _store_recommendations(self, recs: List[Dict]):
        """Persist recommendations to the trade DB learning_recommendations table."""
        if not recs:
            return
        try:
            conn = sqlite3.connect(self._trade_db, timeout=30.0)
            cursor = conn.cursor()
            now = dt.datetime.utcnow().isoformat()
            for rec in recs:
                cursor.execute(
                    "SELECT COUNT(*) FROM learning_recommendations WHERE recommendation_text=? AND is_active=1",
                    (rec["text"],)
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "INSERT INTO learning_recommendations (created_at, category, recommendation_text, supporting_evidence) VALUES (?,?,?,?)",
                        (now, rec["category"], rec["text"], rec["evidence"])
                    )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Store recommendation error: {e}")

    def get_latest_insights(self, period: str = "daily") -> Dict:
        """Run on-demand analysis and return insights immediately."""
        if period == "weekly":
            return self.run_weekly_analysis()
        elif period == "monthly":
            return self.run_monthly_analysis()
        else:
            return self.run_daily_analysis()


# Singleton
learning_engine_hie = LearningEngineHIE()
