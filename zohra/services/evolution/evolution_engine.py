# ZOHRA OS — Evolution Engine
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("zohra.evolution.core")

class MetricPoint:
    def __init__(self, subsystem: str, metric_name: str, value: float, unit: str):
        self.subsystem = subsystem
        self.metric_name = metric_name
        self.value = value
        self.unit = unit
        self.timestamp = time.time()

class StrategyRecommendation:
    def __init__(self, rec_id: str, category: str, title: str, description: str, impact: str):
        self.rec_id = rec_id
        self.category = category
        self.title = title
        self.description = description
        self.impact = impact
        self.status = "PENDING"  # PENDING, APPROVED, DISMISSED

class EvolutionEngine:
    """
    The highest intelligence layer of Zohra OS.
    Monitors health, detects bottlenecks, and generates optimization plans.
    """
    def __init__(self):
        self.metrics: List[MetricPoint] = []
        self.recommendations: Dict[str, StrategyRecommendation] = {}
        logger.info("Evolution Engine initialized.")

    def _seed_default_recommendations(self):
        """Seeds default recommendations for initial dashboard display."""
        recs = [
            StrategyRecommendation(
                rec_id="rec_opt_091",
                category="latency",
                title="Switch Voice STT to Local Whisper ONNX",
                description="Average network latency to Deepgram is 480ms. Switching to local Whisper ONNX will reduce latency to 85ms.",
                impact="Latency reduced by 82%"
            ),
            StrategyRecommendation(
                rec_id="rec_opt_092",
                category="cost",
                title="Enable Semantic Query Caching",
                description="28% of user queries in the last 24 hours are repetitive. Enabling caching will reduce API costs by 22%.",
                impact="API cost reduced by 22%"
            )
        ]
        for r in recs:
            self.recommendations[r.rec_id] = r

    def log_metric(self, subsystem: str, name: str, value: float, unit: str = "ms"):
        """Logs a new performance metric point."""
        point = MetricPoint(subsystem, name, value, unit)
        self.metrics.append(point)
        logger.debug(f"Logged metric: {subsystem}.{name} = {value}{unit}")

    def calculate_health_scores(self) -> Dict[str, float]:
        """Calculates health scores (0-100) for each major division."""
        # Baseline scores that fluctuate slightly based on logged metrics
        scores = {
            "trading": None,
            "voice": None,
            "vision": None,
            "automation": None,
            "system": None
        }
        
        # Adjust Voice score if high latency is logged
        voice_latencies = [m.value for m in self.metrics if m.subsystem == "voice" and m.metric_name == "latency"]
        if voice_latencies:
            avg_lat = sum(voice_latencies) / len(voice_latencies)
            if avg_lat > 300:
                scores["voice"] = max(50.0, 84.0 - (avg_lat - 300) * 0.1)
                
        # Calculate overall system score as the average
        measured = [v for k, v in scores.items() if k != "system" and v is not None]
        scores["system"] = sum(measured) / len(measured) if measured else None
        return scores

    def resolve_recommendation(self, rec_id: str, approved: bool) -> bool:
        """Approves or dismisses an optimization recommendation."""
        if rec_id in self.recommendations:
            rec = self.recommendations[rec_id]
            rec.status = "APPROVED" if approved else "DISMISSED"
            logger.info(f"Recommendation {rec_id} resolved as: {rec.status}")
            return True
        return False
