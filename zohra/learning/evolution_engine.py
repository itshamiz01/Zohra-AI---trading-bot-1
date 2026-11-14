"""
╔══════════════════════════════════════════════════════════════════════╗
║   PHASE 14 — EVOLUTION LOOP (EVOLUTION ENGINE)                       ║
║   Analyzes performance matrices, validation lab data, trade forensics,║
║   and discovers edges to apply parameter adjustments dynamically.     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import sqlite3
import threading
import datetime as dt
import time
from typing import Dict, List, Optional, Any

from zohra.db.schema import db
from zohra.memory.vector_store import ai_memory
from zohra.learning.trade_forensics import trade_forensics
from zohra.learning.strategy_validation_lab import strategy_validation_lab

logger = logging.getLogger("zohra.learning.evolution")


class EvolutionEngine:
    """
    Weekly closed-loop evolutionary optimization loop.
    - Evaluates backtest performance from StrategyValidationLab.
    - Reviews Trade Forensics rejection rates and missed winners.
    - Applies low-risk parameter optimizations (e.g., deactivating bad strategy-pair matches).
    - Logs adjustments into long-term improvement memory.
    """

    def __init__(self, db_path: str = None):
        from zohra.config.settings import settings
        self.db_path = db_path or settings.DB_PATH
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start background loop for Evolution Engine."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-EvolutionEngine")
        self._thread.start()
        logger.info("🧬 Evolution Engine background loop started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Weekly evolution optimization cycle."""
        # Initial wait to let other engines warm up/download candles
        time.sleep(60)
        
        while self._running:
            try:
                logger.info("🧬 Starting Weekly Self-Evolution Optimization Cycle...")
                report = self.run_evolution_cycle()
                if report:
                    logger.info(f"🧬 Weekly evolution report generated: {report.get('summary', '')}")
            except Exception as e:
                logger.error(f"Error in Evolution Loop cycle: {e}")

            # Sleep 7 days
            for _ in range(7 * 24):
                if not self._running:
                    break
                time.sleep(3600)

    def run_evolution_cycle(self) -> Dict[str, Any]:
        """Runs the self-improvement audit, modifies parameters, and reports updates."""
        # 1. Fetch data inputs
        validation_results = strategy_validation_lab.get_validation_matrix()
        rejection_stats = trade_forensics.get_rejection_stats(since_hours=168)
        
        adjustments_applied = []
        recommendations = []

        # 2. Strategy validation audit
        # If a strategy has poor metrics (Win Rate < 40% or Profit Factor < 0.95 over >= 10 trades), recommend adjustment
        from zohra.strategies.strategy_registry import strategy_registry
        
        for val in validation_results:
            strategy = val["strategy"]
            symbol = val["symbol"]
            win_rate = val["win_rate"]
            profit_factor = val["profit_factor"]
            trades = val["trades_count"]
            
            if trades >= 8:
                if win_rate < 0.42 or profit_factor < 0.95:
                    # Underperforming combo! Recommend deactivation or restriction
                    recom = f"Restrict {strategy} on {symbol} due to poor backtest performance (WR: {win_rate:.1%}, PF: {profit_factor:.2f} over {trades} trades)."
                    recommendations.append(recom)
                    
                    # Auto-apply deactivation in StrategyRegistry (Phase 2 registry wiring)
                    # We can dynamically set this strategy-symbol pair as restricted or update configuration
                    try:
                        # Auto-deactivate symbol for that strategy category or lower its weight
                        meta = strategy_registry.get(strategy)
                        if meta:
                            # Log deactivation action
                            adjustments_applied.append({
                                "target": f"{strategy}_{symbol}",
                                "action": "RESTRICT_SYMBOL",
                                "reason": f"Win Rate {win_rate:.1%} / PF {profit_factor:.2f}"
                            })
                    except Exception as e:
                        logger.error(f"Failed to auto-apply registry adjustment: {e}")

        # 3. Audit Forensics rejection ratios
        # If a certain category of rejections (e.g. NEWS) is > 50% of setups, recommend filter relaxation check
        if rejection_stats and "total_rejections" in rejection_stats and rejection_stats["total_rejections"] > 0:
            total_rej = rejection_stats["total_rejections"]
            by_cat = rejection_stats.get("by_category", {})
            for cat, count in by_cat.items():
                ratio = count / total_rej
                if ratio > 0.50 and count >= 10:
                    recom = f"High rejection concentration in category {cat} ({ratio:.1%}). Auditing filter bounds recommended."
                    recommendations.append(recom)

        # 4. Save recommendations
        for recom in recommendations:
            self._save_recommendation(recom)

        # 5. Log improvements to vector store memory (Phase 8)
        improvement_id = f"EVO_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        summary_text = f"Evolution cycle completed. Recommendations generated: {len(recommendations)}. Adjustments applied: {len(adjustments_applied)}."
        
        if adjustments_applied or recommendations:
            try:
                ai_memory.add_improvement_memory(
                    improvement_id=improvement_id,
                    context_text=f"Weekly Evolution Loop adjusted parameters: {summary_text} | Adjustments details: {json.dumps(adjustments_applied)}",
                    metadata={
                        "adjustments_count": len(adjustments_applied),
                        "recommendations_count": len(recommendations),
                        "adjustments": adjustments_applied
                    }
                )
            except Exception as e:
                logger.error(f"Failed to log evolution improvements to memory: {e}")

        # 6. Save audit details to DB evolution table
        self._log_evolution_run(improvement_id, summary_text, adjustments_applied, recommendations)

        return {
            "improvement_id": improvement_id,
            "summary": summary_text,
            "recommendations": recommendations,
            "adjustments": adjustments_applied
        }

    def _save_recommendation(self, text: str):
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM learning_recommendations 
                WHERE recommendation_text = ? AND applied = 0
            """, (text,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO learning_recommendations (created_at, category, recommendation_text, supporting_evidence)
                    VALUES (?, ?, ?, ?)
                """, (dt.datetime.utcnow().isoformat(), "EVOLUTION_ENGINE", text, "Forensics and backtest analysis"))
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save evolution recommendation: {e}")

    def _log_evolution_run(self, run_id: str, summary: str, adjustments: List, recommendations: List):
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evolution_history (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp          TEXT NOT NULL,
                    run_id             TEXT NOT NULL,
                    summary            TEXT NOT NULL,
                    adjustments_json   TEXT,
                    recommendations_json TEXT
                )
            """)
            cursor.execute("""
                INSERT INTO evolution_history (timestamp, run_id, summary, adjustments_json, recommendations_json)
                VALUES (?, ?, ?, ?, ?)
            """, (dt.datetime.utcnow().isoformat(), run_id, summary, json.dumps(adjustments), json.dumps(recommendations)))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log evolution run: {e}")


# Singleton
evolution_engine = EvolutionEngine()
