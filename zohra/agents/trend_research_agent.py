"""
╔══════════════════════════════════════════════════════════════════════╗
║   PHASE 13 — TREND RESEARCH AGENT                                    ║
║   Analyzes EMA Cross, Pullback, and Trendline Continuation,           ║
║   writing trend intelligence to long-term memory.                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import time
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any

from zohra.memory.vector_store import ai_memory

logger = logging.getLogger("zohra.agents.trend_research")


class TrendResearchAgent:
    """
    Dedicated research agent studying Trend Following concepts:
    - Studies EMA golden/death cross and pullbacks.
    - Runs statistical analysis of trend continuity.
    - Writes findings to strategy_memory.
    """

    def __init__(self, db_path: str = None):
        from zohra.hie.historical_data_engine import historical_data_engine
        self.db_path = db_path or historical_data_engine.db_path_hie
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-TrendResearch")
        self._thread.start()
        logger.info("🕵️ Trend Research Agent started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        time.sleep(35) # Warmup
        while self._running:
            try:
                self.conduct_trend_research()
            except Exception as e:
                logger.error(f"Error during Trend research cycle: {e}")
            
            # Run every 6 hours
            for _ in range(6):
                if not self._running:
                    break
                time.sleep(3600)

    def conduct_trend_research(self):
        """Analyze historical setups and outcomes for Trend types."""
        logger.info("🕵️ Trend Research Agent conducting structural analysis...")
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hie_outcomes'")
        if not cursor.fetchone():
            conn.close()
            return

        cursor.execute("""
            SELECT s.setup_type, s.symbol, s.direction, o.outcome
            FROM hie_setups s
            JOIN hie_outcomes o ON s.id = o.setup_id
            WHERE s.setup_type IN ('EMACross', 'TrendPullback', 'TrendlineContinuation')
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return

        stats = {}
        for s_type, sym, direction, outcome in rows:
            key = (s_type, sym)
            stats.setdefault(key, {"wins": 0, "total": 0})
            stats[key]["total"] += 1
            if outcome == 1:
                stats[key]["wins"] += 1

        for (s_type, sym), data in stats.items():
            if data["total"] >= 5:
                win_rate = data["wins"] / data["total"]
                finding_id = f"TREND_FINDING_{sym}_{s_type}_{int(time.time())}"
                finding_text = f"Trend Research: Setup {s_type} on {sym} has historical win rate of {win_rate:.1%} over {data['total']} setups."
                
                try:
                    ai_memory.add_strategy_memory(
                        strategy_id=finding_id,
                        context_text=finding_text,
                        metadata={
                            "research_area": "Trend",
                            "setup_type": s_type,
                            "symbol": sym,
                            "win_rate": win_rate,
                            "total_samples": data["total"]
                        }
                    )
                    logger.debug(f"Logged Trend finding: {finding_text}")
                except Exception as e:
                    logger.error(f"Failed to write Trend research finding to memory: {e}")


# Singleton
trend_research_agent = TrendResearchAgent()
