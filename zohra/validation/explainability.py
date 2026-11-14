"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — AI EXPLAINABILITY ENGINE                       ║
║     Traceable & Explainable Decision Logging for Every Trade        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

from zohra.memory.vector_store import AIMemory
from zohra.config.settings import settings

logger = logging.getLogger("zohra.validation.explainability")


class AIExplainabilityEngine:
    """
    Translates raw algorithmic signal metrics into human-readable and
    audit-ready explainability profiles, storing them inside both
    the local SQLite DB and the vector store memory.
    """

    def __init__(self):
        self.memory = AIMemory()
        self._init_db()

    def _init_db(self):
        """Initialize decision_explanations database table."""
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decision_explanations (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    explanation_text TEXT NOT NULL,
                    technical_payload TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error creating explainability tables: {e}")

    def explain_decision(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes a PipelineDecision data payload, formulates the text summary,
        and saves it to the SQLite db & long-term vector memory.
        """
        decision_id = pipeline_data.get("decision_id", f"dec_{int(datetime.utcnow().timestamp())}")
        symbol = pipeline_data.get("symbol", "UNKNOWN")
        decision = pipeline_data.get("decision", "WAIT")
        direction = pipeline_data.get("direction", "NEUTRAL")
        confidence = pipeline_data.get("confidence", 50.0)
        
        # Build explanation
        narrative = self._generate_narrative(pipeline_data)
        technical_str = json.dumps(pipeline_data)

        # Save to SQLite
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO decision_explanations 
                (id, timestamp, symbol, decision, direction, confidence, explanation_text, technical_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (decision_id, datetime.utcnow().isoformat(), symbol, decision, direction, confidence, narrative, technical_str))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save explanation to SQLite: {e}")

        # Save to AIMemory vector store
        try:
            self.memory.add_trade_experience(
                trade_id=decision_id,
                context_text=narrative,
                category=AIMemory.MEMORY_STRATEGY if decision in ("BUY", "SELL") else AIMemory.MEMORY_ERROR,
                metadata={
                    "symbol": symbol,
                    "decision": decision,
                    "direction": direction,
                    "confidence": confidence,
                    "strategy": pipeline_data.get("strategy_used", "")
                }
            )
        except Exception as e:
            logger.error(f"Failed to log explanation to vector store: {e}")

        return {
            "decision_id": decision_id,
            "narrative": narrative,
            "payload": pipeline_data
        }

    def _generate_narrative(self, data: Dict[str, Any]) -> str:
        """Formulate a comprehensive human-readable decision narrative."""
        symbol = data.get("symbol", "Asset")
        decision = data.get("decision", "WAIT")
        direction = data.get("direction", "NEUTRAL")
        confidence = data.get("confidence", 50.0)
        reasons = data.get("reasons", [])

        # Regime details
        regime_info = "N/A"
        if data.get("regime"):
            regime = data["regime"]
            regime_info = f"{regime.get('enhanced_regime', 'ranging')} regime (confidence: {regime.get('confidence', 50)}%)"

        narrative_parts = [
            f"Decision Audit for {symbol}: The system issued a {decision} ({direction}) warning with a combined confidence of {confidence:.1f}%.",
            f"Market Context: The asset is currently operating inside a {regime_info}.",
        ]

        if data.get("mtf_alignment"):
            mtf = data["mtf_alignment"]
            narrative_parts.append(
                f"Multi-Timeframe Status: Observed {mtf.get('aligned_count', 0)} out of {mtf.get('total_analyzed', 0)} aligned timeframes with HTF bias: {mtf.get('higher_tf_bias', 'NEUTRAL')}."
            )

        if data.get("smc_signal"):
            smc = data["smc_signal"]
            narrative_parts.append(
                f"Smart Money Flow: Sweep status matches {smc.get('bias', 'NEUTRAL')} with displacement count of {smc.get('confluence_count', 0)} blocks."
            )

        if not data.get("macro_clearance", True):
            narrative_parts.append(
                f"Macro Blocks: High severity warnings active. Events: {', '.join(data.get('macro_events_nearby', []))}."
            )

        if reasons:
            narrative_parts.append("Reasoning Log:")
            for r in reasons:
                narrative_parts.append(f" - {r}")

        return "\n".join(narrative_parts)

    def get_explanation(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Fetch explanation details by ID."""
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM decision_explanations WHERE id = ?", (decision_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "symbol": row["symbol"],
                    "decision": row["decision"],
                    "direction": row["direction"],
                    "confidence": row["confidence"],
                    "explanation_text": row["explanation_text"],
                    "technical_payload": json.loads(row["technical_payload"])
                }
        except Exception as e:
            logger.error(f"Failed to fetch explanation: {e}")
        return None

    def list_explanations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent decision explanations."""
        results = []
        try:
            conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, timestamp, symbol, decision, direction, confidence, explanation_text FROM decision_explanations ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            conn.close()
            
            for row in rows:
                results.append({
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "symbol": row["symbol"],
                    "decision": row["decision"],
                    "direction": row["direction"],
                    "confidence": row["confidence"],
                    "explanation_text": row["explanation_text"]
                })
        except Exception as e:
            logger.error(f"Failed to list explanations: {e}")
        return results


# Singleton
explainability_engine = AIExplainabilityEngine()
