# ZOHRA OS — Workflow Engine
import logging
import asyncio
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger("zohra.automation.workflow")

class WorkflowStep:
    """Represents a single executable step in an automation workflow."""
    def __init__(self, step_id: str, action: str, params: Dict[str, Any], depend_on: List[str] = None):
        self.step_id = step_id
        self.action = action
        self.params = params
        self.depend_on = depend_on or []
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
        self.result = None
        self.error = None
        self.retry_limit = 3
        self.retry_count = 0

class Workflow:
    """Manages the state and execution loop of a multi-step task."""
    def __init__(self, workflow_id: str, name: str, steps: List[WorkflowStep]):
        self.workflow_id = workflow_id
        self.name = name
        self.steps = {s.step_id: s for s in steps}
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
        self.start_time = None
        self.end_time = None

    def is_runnable(self, step: WorkflowStep) -> bool:
        """Check if all parent steps are completed."""
        if step.status != "PENDING":
            return False
        for parent_id in step.depend_on:
            if parent_id not in self.steps or self.steps[parent_id].status != "COMPLETED":
                return False
        return True

    def get_runnable_steps(self) -> List[WorkflowStep]:
        return [s for s in self.steps.values() if self.is_runnable(s)]

    def is_completed(self) -> bool:
        return all(s.status == "COMPLETED" for s in self.steps.values())

    def is_failed(self) -> bool:
        return any(s.status == "FAILED" for s in self.steps.values())

class WorkflowEngine:
    """Executes workflows and manages step dispatching and retries."""
    def __init__(self):
        self.active_workflows: Dict[str, Workflow] = {}
        logger.info("Workflow Engine initialized.")

    async def execute_workflow(self, workflow: Workflow, dispatcher_fn) -> str:
        """Runs the workflow execution loop asynchronously."""
        self.active_workflows[workflow.workflow_id] = workflow
        workflow.status = "RUNNING"
        workflow.start_time = time.time()
        logger.info(f"Starting workflow: '{workflow.name}' (ID: {workflow.workflow_id})")

        try:
            while not workflow.is_completed() and not workflow.is_failed():
                runnable = workflow.get_runnable_steps()
                if not runnable:
                    # Check for deadlocks or circular dependencies
                    if any(s.status == "RUNNING" for s in workflow.steps.values()):
                        await asyncio.sleep(0.1)
                        continue
                    else:
                        workflow.status = "FAILED"
                        logger.error(f"Workflow deadlock detected for '{workflow.name}'. Aborting.")
                        break

                # Execute all runnable steps in parallel
                tasks = [self._execute_step(workflow, step, dispatcher_fn) for step in runnable]
                await asyncio.gather(*tasks)

            if workflow.is_completed():
                workflow.status = "COMPLETED"
                logger.info(f"Workflow '{workflow.name}' completed successfully in {time.time() - workflow.start_time:.2f}s.")
            else:
                workflow.status = "FAILED"
                logger.error(f"Workflow '{workflow.name}' failed.")
                
        except Exception as e:
            workflow.status = "FAILED"
            logger.error(f"Error executing workflow '{workflow.name}': {e}")
        finally:
            workflow.end_time = time.time()
            
        return workflow.status

    async def _execute_step(self, workflow: Workflow, step: WorkflowStep, dispatcher_fn):
        step.status = "RUNNING"
        logger.info(f"Executing step '{step.step_id}' [{step.action}]")
        
        while step.retry_count <= step.retry_limit:
            try:
                # Dispatch action to the appropriate handler
                result = await dispatcher_fn(step.action, step.params)
                step.status = "COMPLETED"
                step.result = result
                logger.info(f"Step '{step.step_id}' completed successfully.")
                return
            except Exception as e:
                if isinstance(e, (PermissionError, ValueError, NotImplementedError)):
                    step.status = "FAILED"
                    step.error = str(e)
                    return
                step.retry_count += 1
                logger.warning(f"Step '{step.step_id}' failed (Attempt {step.retry_count}/{step.retry_limit + 1}): {e}")
                if step.retry_count > step.retry_limit:
                    step.status = "FAILED"
                    step.error = str(e)
                    logger.error(f"Step '{step.step_id}' reached max retries. Failing step.")
                    return
                await asyncio.sleep(0.5 * step.retry_count) # Exponential backoff
