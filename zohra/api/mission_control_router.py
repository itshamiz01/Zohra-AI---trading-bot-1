"""
╔══════════════════════════════════════════════════════════════════════╗
║         ZOHRA — TRADING MISSION CONTROL API ROUTER                   ║
║   REST Endpoints for Supreme Commands, Rotations & Opportunity Feeds ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any

try:
    from fastapi import APIRouter, Query, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger("zohra.api.mission_control")

router = None

if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/api/mission-control", tags=["Trading Mission Control"])

    # ─── Pydantic Models ──────────────────────────────────────

    class CommandRequest(BaseModel):
        command: str

    class ActionRequest(BaseModel):
        action: str  # rotate_capital / set_risk_mode / toggle_strategy
        broker: Optional[str] = None
        target_pct: Optional[float] = None
        risk_mode: Optional[str] = None
        strategy_name: Optional[str] = None
        active: Optional[bool] = None

    # ─── Endpoints ────────────────────────────────────────────

    @router.get("/status")
    async def get_mission_status():
        """Get trading mission control status summary."""
        try:
            from zohra.mission_control.mission_control import mission_control
            from zohra.mission_control.self_healing import self_healing_engine
            
            diag = self_healing_engine.get_latest_diagnostics()
            summary = mission_control.get_status_summary()
            
            return {
                "status": "success",
                "mission_control": summary,
                "diagnostics": diag,
                "recovery_logs": self_healing_engine.recovery_logs[-10:]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/command")
    async def post_commander_prompt(req: CommandRequest):
        """Conversational text interface to query and command the trading system."""
        try:
            from zohra.mission_control.commander import ai_commander
            res = ai_commander.process_natural_command(req.command)
            return {"status": "success", "result": res}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/opportunities")
    async def get_ranked_opps():
        """Fetch real-time ranked opportunities across all markets."""
        try:
            from zohra.mission_control.mission_control import mission_control
            opps = mission_control.get_ranked_opportunities()
            return {"status": "success" if opps else "empty", "opportunities": opps}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/correlations")
    async def get_correlations_matrix():
        """Get live asset correlation matrices."""
        try:
            from zohra.mission_control.mission_control import mission_control
            matrix = mission_control.get_correlation_matrix()
            return {"status": "success" if matrix else "unavailable", "correlation_matrix": matrix}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/action")
    async def post_action_trigger(req: ActionRequest):
        """Execute specific manual overrides."""
        try:
            from zohra.mission_control.mission_control import mission_control
            
            if req.action == "rotate_capital" and req.broker and req.target_pct is not None:
                mission_control.rotate_capital(req.broker, req.target_pct)
                return {"status": "success", "message": f"Rotated capital for {req.broker} to {req.target_pct}%"}
            
            elif req.action == "set_risk_mode" and req.risk_mode:
                if req.risk_mode not in {"conservative", "moderate", "aggressive", "defensive"}:
                    raise HTTPException(status_code=422, detail="Unknown risk mode")
                mission_control.set_risk_mode(req.risk_mode)
                return {"status": "success", "message": f"Global risk mode updated to {req.risk_mode}"}
            
            elif req.action == "toggle_strategy" and req.strategy_name and req.active is not None:
                ok = mission_control.toggle_strategy(req.strategy_name, req.active)
                if ok:
                    return {"status": "success", "message": f"Strategy {req.strategy_name} set to active={req.active}"}
                else:
                    return {"status": "error", "message": f"Strategy {req.strategy_name} not found"}
            
            raise HTTPException(status_code=400, detail="Invalid action request parameters")
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
