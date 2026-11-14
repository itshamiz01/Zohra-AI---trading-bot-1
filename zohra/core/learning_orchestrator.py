"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — LEARNING ORCHESTRATOR                        ║
║         Experience Ingestion, Diagnostics, and Mastery Tuning        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import hashlib
from typing import Dict, Any, List
from zohra.core.learning_memory import learning_memory
from zohra.core.mistake_detector import mistake_detector
from zohra.core.shadow_ai_analyst import shadow_ai_analyst
from zohra.core.confidence_calibrator import confidence_calibrator

logger = logging.getLogger("zohra.learning.orchestrator")

class LearningOrchestrator:
    """
    Coordinates the learning pipeline across trade outcomes, mistakes,
    and shadow simulations, updating the system's long-term memory.
    """
    def learn_from_trade_close(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        trade_id = trade_data.get("trade_id", "")
        pnl = trade_data.get("pnl_usd", 0.0)
        symbol = trade_data.get("symbol", "")
        
        logger.info(f"🧠 Learning Orchestrator: Ingesting closed trade {trade_id}...")
        
        # 1. Detect Mistakes
        mistakes = mistake_detector.analyze_trade_for_mistakes(trade_data)
        for m in mistakes:
            learning_memory.add_mistake(trade_id, m["severity"], m["type"], m["description"])
            
        # 2. Analyze Shadow Alternatives
        shadow_report = shadow_ai_analyst.analyze_shadow_performance(trade_id, pnl)
        
        # 3. Formulate Lesson
        result_str = "WIN" if pnl > 0 else "LOSS"
        lesson_parts = [
            f"Trade on {symbol} closed as {result_str} (${pnl:+.2f})."
        ]
        if mistakes:
            lesson_parts.append(f"Detected {len(mistakes)} mistake(s): {', '.join(m['type'] for m in mistakes)}.")
        else:
            lesson_parts.append("Perfect execution. No mistakes detected.")
            
        if shadow_report["best_alternative"] != "LIVE":
            lesson_parts.append(f"Optimization hint: The virtual {shadow_report['best_alternative']} shadow trade outperformed live by ${shadow_report['pnl_diff_usd']:.2f}.")
            
        lesson_text = " ".join(lesson_parts)
        lesson_id = hashlib.md5(f"{trade_id}_lesson".encode()).hexdigest()[:8]
        
        # Save lesson
        learning_memory.add_lesson(
            lesson_id=lesson_id,
            source_type="TRADE",
            source_id=trade_id,
            category="Risk" if mistakes else "Execution",
            lesson_text=lesson_text
        )
        
        # 4. Update Domain Mastery XP
        xp_gained = 50 if pnl > 0 else 20 # Gain more XP on winning trades
        if mistakes:
            xp_gained = max(5, xp_gained - 15) # Penalty for mistakes
            
        learning_memory.update_mastery("Risk Management", xp_gained)
        learning_memory.update_mastery("SMC", xp_gained)
        
        # 5. Run Calibration
        calibration = confidence_calibrator.calibrate_confidence_scores()
        
        return {
            "trade_id": trade_id,
            "result": result_str,
            "pnl": pnl,
            "mistakes_count": len(mistakes),
            "best_alternative": shadow_report["best_alternative"],
            "lesson_text": lesson_text,
            "xp_gained": xp_gained,
            "calibration": calibration
        }

# Singleton
learning_orchestrator = LearningOrchestrator()
