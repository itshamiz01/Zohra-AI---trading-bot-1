"""
╔══════════════════════════════════════════════════════════════════════╗
║   PHASE 13 — CORRELATION RESEARCH AGENT                              ║
║   Analyzes inter-pair currency correlations and USD dominance,       ║
║   writing correlation risk intelligence to long-term memory.         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import time
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from zohra.memory.vector_store import ai_memory

logger = logging.getLogger("zohra.agents.correlation_research")


class CorrelationResearchAgent:
    """
    Dedicated research agent studying Correlation:
    - Studies price correlations across major currency pairs.
    - Highlights USD dominance or clustering vulnerabilities.
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
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-CorrelationResearch")
        self._thread.start()
        logger.info("🕵️ Correlation Research Agent started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        time.sleep(45) # Warmup
        while self._running:
            try:
                self.conduct_correlation_research()
            except Exception as e:
                logger.error(f"Error during Correlation research cycle: {e}")
            
            # Run every 6 hours
            for _ in range(6):
                if not self._running:
                    break
                time.sleep(3600)

    def conduct_correlation_research(self):
        """Analyze price correlations using HIE candles."""
        logger.info("🕵️ Correlation Research Agent running portfolio correlation audit...")
        
        from zohra.hie.historical_data_engine import HIE_SYMBOLS, historical_data_engine
        
        # Load last 100 H1 candles for major symbols
        major_symbols = [s for s in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"] if s in HIE_SYMBOLS]
        
        data = {}
        for sym in major_symbols:
            df = historical_data_engine.get_candles(sym, "H1", limit=100)
            if not df.empty and len(df) >= 50:
                data[sym] = df["close"].values[-50:] # align last 50 candles
                
        if len(data) < 2:
            return

        # Build correlation matrix
        df_corr = pd.DataFrame(data).corr()
        
        # Discover strong correlation edges
        for i in range(len(df_corr.columns)):
            for j in range(i + 1, len(df_corr.columns)):
                sym1 = df_corr.columns[i]
                sym2 = df_corr.columns[j]
                corr_val = float(df_corr.iloc[i, j])
                
                if abs(corr_val) >= 0.75:
                    finding_id = f"CORR_FINDING_{sym1}_{sym2}_{int(time.time())}"
                    relationship = "positive" if corr_val > 0 else "negative"
                    finding_text = f"Correlation Research: Strong {relationship} correlation of {corr_val:.2f} discovered between {sym1} and {sym2}."
                    
                    try:
                        ai_memory.add_strategy_memory(
                            strategy_id=finding_id,
                            context_text=finding_text,
                            metadata={
                                "research_area": "Correlation",
                                "symbol_1": sym1,
                                "symbol_2": sym2,
                                "correlation_coefficient": corr_val,
                                "relationship_type": relationship
                            }
                        )
                        logger.debug(f"Logged Correlation finding: {finding_text}")
                    except Exception as e:
                        logger.error(f"Failed to write Correlation research finding to memory: {e}")


# Singleton
correlation_research_agent = CorrelationResearchAgent()
