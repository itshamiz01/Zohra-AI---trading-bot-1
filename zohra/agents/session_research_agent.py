"""
╔══════════════════════════════════════════════════════════════════════╗
║   PHASE 13 — SESSION RESEARCH AGENT                                  ║
║   Analyzes London, NY, Asian, and Overlap session outcomes,          ║
║   writing session intelligence directly to long-term memory.         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import time
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any

from zohra.memory.vector_store import ai_memory

logger = logging.getLogger("zohra.agents.session_research")


class SessionResearchAgent:
    """
    Dedicated research agent studying Session intelligence:
    - Analyzes trade performance relative to session times.
    - Focuses on London open, NY open, and overlapping windows.
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
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-SessionResearch")
        self._thread.start()
        logger.info("🕵️ Session Research Agent started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        time.sleep(40) # Warmup
        while self._running:
            try:
                self.conduct_session_research()
            except Exception as e:
                logger.error(f"Error during Session research cycle: {e}")
            
            # Run every 6 hours
            for _ in range(6):
                if not self._running:
                    break
                time.sleep(3600)

    def conduct_session_research(self):
        """Analyze historical setups and outcomes grouped by trading sessions."""
        logger.info("🕵️ Session Research Agent conducting timing audits...")
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hie_outcomes'")
        if not cursor.fetchone():
            conn.close()
            return

        cursor.execute("""
            SELECT s.session, s.symbol, o.outcome
            FROM hie_setups s
            JOIN hie_outcomes o ON s.id = o.setup_id
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return

        stats = {}
        for session, sym, outcome in rows:
            key = (session, sym)
            stats.setdefault(key, {"wins": 0, "total": 0})
            stats[key]["total"] += 1
            if outcome == 1:
                stats[key]["wins"] += 1

        for (session, sym), data in stats.items():
            if data["total"] >= 5:
                win_rate = data["wins"] / data["total"]
                finding_id = f"SESS_FINDING_{sym}_{session}_{int(time.time())}"
                finding_text = f"Session Research: Setup performance on {sym} during {session} session has win rate of {win_rate:.1%} over {data['total']} trades."
                
                try:
                    ai_memory.add_strategy_memory(
                        strategy_id=finding_id,
                        context_text=finding_text,
                        metadata={
                            "research_area": "Session",
                            "session": session,
                            "symbol": sym,
                            "win_rate": win_rate,
                            "total_samples": data["total"]
                        }
                    )
                    logger.debug(f"Logged Session finding: {finding_text}")
                except Exception as e:
                    logger.error(f"Failed to write Session research finding to memory: {e}")


# Singleton
session_research_agent = SessionResearchAgent()
