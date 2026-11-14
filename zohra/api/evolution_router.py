# ZOHRA OS — Evolution API Router & Management Gateway
import logging
from typing import Dict, Any
from pydantic import BaseModel

try:
    from fastapi import APIRouter, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from zohra.services.evolution.evolution_engine import EvolutionEngine
    from zohra.services.evolution.cost_optimizer import CostOptimizer

    logger = logging.getLogger("zohra.api.evolution")
    router = APIRouter(prefix="/api/v1/evolution", tags=["Evolution Engine Services"])
    
    engine = EvolutionEngine()
    cost_optimizer = CostOptimizer()

    class ResolveRecommendationPayload(BaseModel):
        rec_id: str
        approved: bool

    @router.get("/health")
    async def get_system_health():
        """Returns health scores, daily costs, and resource telemetry."""
        try:
            health_scores = engine.calculate_health_scores()
            costs = cost_optimizer.get_accumulated_costs()
            
            return {
                "status": "success",
                "health_scores": health_scores,
                "costs": costs,
                "system_health_score": health_scores["system"]
            }
        except Exception as e:
            logger.error(f"Failed to fetch system health: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/recommendations")
    async def list_recommendations():
        """Lists all active strategy recommendations."""
        try:
            results = []
            for rid, rec in engine.recommendations.items():
                results.append({
                    "id": rid,
                    "category": rec.category,
                    "title": rec.title,
                    "description": rec.description,
                    "impact": rec.impact,
                    "status": rec.status
                })
            return {"status": "success", "recommendations": results}
        except Exception as e:
            logger.error(f"Failed to list recommendations: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/recommendations/resolve")
    async def resolve_recommendation(payload: ResolveRecommendationPayload):
        """Approves or dismisses an optimization recommendation."""
        try:
            success = engine.resolve_recommendation(payload.rec_id, payload.approved)
            if success:
                return {"status": "success", "message": f"Recommendation '{payload.rec_id}' resolved."}
            else:
                raise HTTPException(status_code=400, detail="Failed to resolve recommendation.")
        except Exception as e:
            logger.error(f"Failed to resolve recommendation: {e}")
            raise HTTPException(status_code=500, detail=str(e))
else:
    router = None
