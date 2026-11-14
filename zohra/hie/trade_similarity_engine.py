"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 8 — TRADE SIMILARITY ENGINE                                 ║
║   Before any live trade: finds top-100 most similar historical       ║
║   setups and returns win rate, avg RR, and confidence level.         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("zohra.hie.similarity")

# Similarity scoring weights
SIMILARITY_WEIGHTS = {
    "symbol":    3.0,   # Exact symbol match is most important
    "direction": 2.0,   # Direction match
    "session":   2.0,   # Session alignment
    "setup_type":1.5,   # Setup type match
    "timeframe": 1.0,   # Timeframe match
}


class TradeSimilarityEngine:
    """
    Before Zohra takes a live trade, this engine queries historical outcomes
    to find the most similar past setups and report their collective statistics.

    Usage:
        result = trade_similarity_engine.find_similar(setup_dict)
        result → {
            "match_count": 378,
            "win_rate": 74.3,
            "avg_rr": 2.4,
            "confidence": "HIGH",
            "best_session": "London",
            "historical_evidence": [...]
        }
    """

    def __init__(self):
        from zohra.hie.historical_data_engine import historical_data_engine
        self._db_path = historical_data_engine.db_path_hie

    def find_similar(
        self,
        symbol: str,
        direction: str,
        session: str,
        setup_type: Optional[str] = None,
        timeframe: Optional[str] = None,
        top_n: int = 100
    ) -> Dict:
        """
        Find historically similar setups and return aggregated statistics.

        Args:
            symbol: Trading symbol
            direction: "LONG" or "SHORT"
            session: Trading session
            setup_type: Optional setup type (BOS, FVG, etc.)
            timeframe: Optional timeframe
            top_n: Number of similar setups to find

        Returns:
            dict with match_count, win_rate, avg_rr, confidence, best_session
        """
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)

            # Build cascading query (most specific → broadest)
            queries = []

            # Level 1: Exact match (symbol + direction + session + setup)
            if setup_type:
                q1 = "SELECT *, 4 as match_level FROM hie_setup_outcomes WHERE symbol=? AND direction=? AND session=? AND setup_type=?"
                p1 = [symbol, direction, session, setup_type]
                queries.append((q1, p1))

            # Level 2: Symbol + direction + session
            q2 = "SELECT *, 3 as match_level FROM hie_setup_outcomes WHERE symbol=? AND direction=? AND session=?"
            queries.append((q2, [symbol, direction, session]))

            # Level 3: Symbol + direction (any session)
            q3 = "SELECT *, 2 as match_level FROM hie_setup_outcomes WHERE symbol=? AND direction=?"
            queries.append((q3, [symbol, direction]))

            # Level 4: Symbol only (any direction, any session)
            q4 = "SELECT *, 1 as match_level FROM hie_setup_outcomes WHERE symbol=?"
            queries.append((q4, [symbol]))

            all_rows = []
            for q, params in queries:
                df = pd.read_sql_query(q, conn, params=params)
                if not df.empty:
                    all_rows.append(df)
                    if df["is_win"].count() >= top_n:
                        break  # Enough data at this specificity level

            if not all_rows:
                return self._empty_result(symbol, direction, session)

            # Combine and deduplicate
            combined = pd.concat(all_rows, ignore_index=True)
            combined = combined.drop_duplicates(subset=["setup_id"] if "setup_id" in combined.columns else None)
            combined = combined.head(top_n * 3)  # Take extra for dedup margin

            # Calculate statistics
            n = len(combined)
            if n == 0:
                return self._empty_result(symbol, direction, session)

            wins = int(combined["is_win"].sum())
            win_rate = round(wins / n * 100, 2)
            avg_rr = round(float(combined["pnl_r"].mean()), 4)
            avg_mfe = round(float(combined["mfe_r"].mean()), 4)
            avg_mae = round(float(combined["mae_r"].mean()), 4)
            reach_1r = round(float(combined["reached_1r"].mean()) * 100, 2)
            reach_2r = round(float(combined["reached_2r"].mean()) * 100, 2)

            # Best session from matched data
            best_session = None
            if "session" in combined.columns:
                sess_wr = combined.groupby("session")["is_win"].mean()
                if not sess_wr.empty:
                    best_session = str(sess_wr.idxmax())

            # Confidence level
            confidence = self._calculate_confidence(n, win_rate, avg_rr)

            # Top recent examples
            evidence = []
            if "timestamp" in combined.columns:
                recent = combined.sort_values("timestamp", ascending=False).head(5)
                for _, row in recent.iterrows():
                    evidence.append({
                        "symbol": str(row.get("symbol", symbol)),
                        "direction": str(row.get("direction", direction)),
                        "session": str(row.get("session", session)),
                        "setup_type": str(row.get("setup_type", "N/A")),
                        "timestamp": str(row.get("timestamp", "")),
                        "outcome": "WIN" if row.get("is_win", 0) else "LOSS",
                        "pnl_r": round(float(row.get("pnl_r", 0)), 2)
                    })

            return {
                "symbol": symbol,
                "direction": direction,
                "session": session,
                "match_count": n,
                "wins": wins,
                "losses": n - wins,
                "win_rate": win_rate,
                "avg_rr": avg_rr,
                "avg_mfe_r": avg_mfe,
                "avg_mae_r": avg_mae,
                "reach_1r_pct": reach_1r,
                "reach_2r_pct": reach_2r,
                "confidence": confidence,
                "best_session": best_session or session,
                "historical_evidence": evidence,
                "data_available": True
            }

        except Exception as e:
            logger.error(f"TradeSimilarity find_similar error: {e}")
            return self._empty_result(symbol, direction, session)
        finally:
            if conn:
                conn.close()

    def find_similar_from_setup(self, setup_dict: Dict) -> Dict:
        """Convenience method that accepts a standard Zohra setup dict."""
        symbol = setup_dict.get("symbol", "")
        direction = setup_dict.get("direction", "LONG")
        session = setup_dict.get("session", "London")
        strategy = setup_dict.get("strategy", "")
        timeframe = setup_dict.get("timeframe", "H1")

        # Map Zohra strategy names to HIE setup types
        setup_type_map = {
            "zohra_v5": "BOS",
            "scalp_m5": "MomentumBreakout",
            "mean_reversion": "TrendPullback",
            "trend_following": "EMACross",
            "breakout": "Breakout",
            "momentumscalp": "MomentumBreakout"
        }
        setup_type = setup_type_map.get(strategy.lower(), None)

        return self.find_similar(
            symbol=symbol,
            direction=direction,
            session=session,
            setup_type=setup_type,
            timeframe=timeframe
        )

    def get_similarity_score(self, symbol: str, direction: str, session: str, setup_type: Optional[str] = None) -> float:
        """
        Return a normalized 0-100 historical similarity score.
        Incorporates win rate, avg RR, and data confidence.
        """
        result = self.find_similar(symbol, direction, session, setup_type)
        if not result.get("data_available"):
            return 50.0

        win_rate = result.get("win_rate", 50)
        avg_rr = result.get("avg_rr", 1.0)
        n = result.get("match_count", 0)

        # Confidence scaling: low sample = regress toward neutral
        confidence_scale = min(1.0, n / 50.0)
        raw = (win_rate * 0.6 + min(avg_rr * 20, 40))
        score = 50 + (raw - 50) * confidence_scale
        return round(max(0, min(100, score)), 2)

    def _calculate_confidence(self, n: int, win_rate: float, avg_rr: float) -> str:
        if n >= 50 and win_rate >= 65 and avg_rr >= 1.5:
            return "HIGH"
        elif n >= 20 and win_rate >= 55:
            return "MEDIUM"
        elif n >= 10:
            return "LOW"
        else:
            return "INSUFFICIENT DATA"

    def _empty_result(self, symbol: str, direction: str, session: str) -> Dict:
        return {
            "symbol": symbol,
            "direction": direction,
            "session": session,
            "match_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "avg_rr": 0,
            "avg_mfe_r": 0,
            "avg_mae_r": 0,
            "reach_1r_pct": 0,
            "reach_2r_pct": 0,
            "confidence": "INSUFFICIENT DATA",
            "best_session": session,
            "historical_evidence": [],
            "data_available": False
        }


# Singleton
trade_similarity_engine = TradeSimilarityEngine()
