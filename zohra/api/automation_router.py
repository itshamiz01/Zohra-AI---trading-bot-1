# ZOHRA OS — Automation API Router & Workflow Gateway
import logging
import asyncio
from typing import Dict, Any, Optional
from pydantic import BaseModel

try:
    from fastapi import APIRouter, HTTPException, BackgroundTasks
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from zohra.services.automation.workflow_engine import WorkflowEngine, Workflow
    from zohra.services.automation.task_planner import TaskPlanner
    from zohra.services.automation.approval_system import ApprovalSystem

    logger = logging.getLogger("zohra.api.automation")
    router = APIRouter(prefix="/api/v1/automation", tags=["Automation Division Services"])
    
    engine = WorkflowEngine()
    planner = TaskPlanner()
    approval_system = ApprovalSystem()

    class TriggerWorkflowPayload(BaseModel):
        command: str

    class ResolveApprovalPayload(BaseModel):
        request_id: str
        approved: bool

    async def dispatch_action(action: str, params: dict) -> dict:
        """Dispatches workflow steps to actual subsystems."""
        logger.info(f"Dispatcher executing action: {action} with params={params}")
        
        from zohra.analytics.workspace_data import research_snapshot
        from zohra.brokers.mt5_broker import mt5_broker
        if action == "trading.get_positions":
            from zohra.db.schema import db
            return {"positions": db.get_open_trades(), "source": "trade journal"}
        if action == "research.get_economic_calendar":
            return research_snapshot()
        if action == "system.status":
            from zohra.analytics.telemetry_provider import get_system_telemetry
            return get_system_telemetry()
        if action == "trading.close_all_positions":
            from zohra.security.permissions import trading_permission_gateway
            decision = trading_permission_gateway.authorize_broker_action(
                action, {"broker": "mt5", "authorization_token": params.get("authorization_token", "")}
            )
            if not decision.approved:
                raise ValueError(decision.reason)
            if not mt5_broker.is_connected():
                raise ValueError("No broker connected to this API process")
            await approval_system.request_approval(action, params)
            return {"positions_closed": mt5_broker.close_all_positions(comment="Approved-Workflow")}
        if action == "file.write_report":
            import json
            from pathlib import Path
            from datetime import datetime, timezone
            from zohra.config.settings import REPORTS_DIR
            from zohra.db.schema import db
            folder = Path(REPORTS_DIR) / "automation"
            folder.mkdir(parents=True, exist_ok=True)
            name = "trading-plan-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".json"
            (folder / name).write_text(json.dumps({"positions": db.get_open_trades(), "research": research_snapshot()}, default=str, indent=2), encoding="utf-8")
            return {"report": name, "download": f"/api/v1/automation/reports/{name}"}
        if action == "voice.speak":
            from zohra.services.voice.tts_connector import TTSConnector
            audio = await asyncio.to_thread(TTSConnector().synthesize, params.get("message", ""))
            return {"audio_bytes": len(audio)}
        raise NotImplementedError(f"Unsupported workflow action: {action}")

    @router.post("/trigger")
    async def trigger_workflow(payload: TriggerWorkflowPayload, background_tasks: BackgroundTasks):
        """Compiles a natural language request and executes it as a background task."""
        try:
            workflow = planner.compile_plan(payload.command)
            
            # Run in background to prevent blocking the HTTP response
            engine.active_workflows[workflow.workflow_id] = workflow
            background_tasks.add_task(engine.execute_workflow, workflow, dispatch_action)
            
            return {
                "status": "success",
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "steps": [s.step_id for s in workflow.steps.values()]
            }
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to trigger workflow: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/workflows")
    async def get_active_workflows():
        """Returns a list of all running and completed workflows."""
        try:
            results = []
            for wf in engine.active_workflows.values():
                results.append({
                    "workflow_id": wf.workflow_id,
                    "name": wf.name,
                    "status": wf.status,
                    "steps": [{
                        "step_id": s.step_id,
                        "action": s.action,
                        "status": s.status,
                        "retry_count": s.retry_count
                        , "result": s.result, "error": s.error
                    } for s in wf.steps.values()]
                })
            return {"status": "success", "workflows": results}
        except Exception as e:
            logger.error(f"Failed to fetch workflows: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/approve")
    async def resolve_approval(payload: ResolveApprovalPayload):
        """Resolves a pending approval request."""
        try:
            if payload.request_id not in approval_system.pending_requests:
                raise HTTPException(status_code=404, detail="Approval request not found")
            approval_system.resolve_request(payload.request_id, payload.approved)
            return {"status": "success", "message": f"Resolved request: {payload.request_id}"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to resolve approval: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    @router.get("/approvals")
    def approvals():
        return {"requests": [{"request_id": r.request_id, "action": r.action, "status": r.status}
                             for r in approval_system.pending_requests.values()]}

    @router.get("/reports/{filename}")
    def report_download(filename: str):
        from pathlib import Path
        from fastapi.responses import FileResponse
        from zohra.config.settings import REPORTS_DIR
        folder = (Path(REPORTS_DIR) / "automation").resolve()
        target = (folder / filename).resolve()
        if target.parent != folder or target.suffix != ".json" or not target.is_file():
            raise HTTPException(status_code=404, detail="Report not found")
        return FileResponse(target, filename=filename, media_type="application/json")
else:
    router = None
