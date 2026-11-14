"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — WORKFLOW ENGINE                            ║
║     Sequential & Programmable Workflows with Branching & Retries     ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable
from zohra.core.base_module import ZohraModule
from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.core.workflow_engine")

class WorkflowStep:
    def __init__(
        self,
        step_id: str,
        handler: Callable[..., Any],
        args: Optional[Dict[str, Any]] = None,
        on_success: Optional[str] = None,
        on_failure: Optional[str] = None,
        max_retries: int = 1,
        delay: float = 1.0,
    ):
        self.step_id = step_id
        self.handler = handler
        self.args = args or {}
        self.on_success = on_success
        self.on_failure = on_failure
        self.max_retries = max_retries
        self.delay = delay
        self.status = "PENDING"  # PENDING / RUNNING / COMPLETED / FAILED
        self.result: Any = None
        self.error: Optional[str] = None

class Workflow:
    def __init__(self, workflow_id: str, name: str):
        self.workflow_id = workflow_id
        self.name = name
        self.steps: Dict[str, WorkflowStep] = {}
        self.status = "PENDING"  # PENDING / RUNNING / COMPLETED / FAILED
        self.current_step_id: Optional[str] = None
        self.history: List[Dict[str, Any]] = []

    def add_step(self, step: WorkflowStep):
        self.steps[step.step_id] = step

class WorkflowEngine(ZohraModule):
    """
    Modular execution engine running sequential, parallel, and conditional step graphs.
    Allows automated and human-in-the-loop workflows.
    """
    def __init__(self):
        super().__init__("WorkflowEngine")
        self.active_workflows: Dict[str, Workflow] = {}
        self.workflow_templates: Dict[str, List[Dict[str, Any]]] = {}

    def initialize(self) -> bool:
        logger.info("Initializing ZOHRA Workflow Engine...")
        # Register a few default template outlines
        self.workflow_templates["morning_briefing"] = [
            {"step_id": "health_check", "on_success": "load_regime"},
            {"step_id": "load_regime",  "on_success": "generate_report"},
            {"step_id": "generate_report"}
        ]
        return True

    def shutdown(self) -> bool:
        logger.info("Shutting down ZOHRA Workflow Engine...")
        self.active_workflows.clear()
        return True

    def create_workflow(self, workflow_id: str, name: str) -> Workflow:
        wf = Workflow(workflow_id, name)
        self.active_workflows[workflow_id] = wf
        return wf

    async def execute_workflow(self, workflow_id: str, start_step_id: str):
        wf = self.active_workflows.get(workflow_id)
        if not wf:
            logger.error(f"Workflow '{workflow_id}' not found.")
            return

        wf.status = "RUNNING"
        current_id = start_step_id
        await event_bus.publish("workflow_started", {"workflow_id": workflow_id, "name": wf.name})

        while current_id:
            step = wf.steps.get(current_id)
            if not step:
                logger.error(f"Step '{current_id}' not found in workflow '{workflow_id}'.")
                wf.status = "FAILED"
                break

            wf.current_step_id = current_id
            step.status = "RUNNING"
            logger.info(f"Executing workflow step: {workflow_id}.{current_id}")

            # Execution with Retry loop
            attempts = 0
            success = False
            while attempts < step.max_retries:
                try:
                    attempts += 1
                    if asyncio.iscoroutinefunction(step.handler):
                        step.result = await step.handler(**step.args)
                    else:
                        step.result = step.handler(**step.args)
                    step.status = "COMPLETED"
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"Step '{current_id}' attempt {attempts} failed: {e}")
                    step.error = str(e)
                    if attempts < step.max_retries:
                        await asyncio.sleep(step.delay)

            wf.history.append({
                "step_id": current_id,
                "status": step.status,
                "attempts": attempts,
                "result": str(step.result) if step.result else None,
                "error": step.error
            })

            if success:
                current_id = step.on_success
            else:
                step.status = "FAILED"
                current_id = step.on_failure
                if not current_id:
                    wf.status = "FAILED"
                    await event_bus.publish("workflow_failed", {"workflow_id": workflow_id, "error": step.error})
                    return

        wf.status = "COMPLETED"
        await event_bus.publish("workflow_completed", {"workflow_id": workflow_id})

    def get_status(self) -> Dict[str, Any]:
        status_info = super().get_status()
        status_info.update({
            "active_workflows_count": len(self.active_workflows),
            "workflows": [
                {
                    "workflow_id": w.workflow_id,
                    "name": w.name,
                    "status": w.status,
                    "current_step": w.current_step_id
                }
                for w in self.active_workflows.values()
            ]
        })
        return status_info

workflow_engine = WorkflowEngine()
