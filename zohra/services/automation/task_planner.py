# ZOHRA OS — Task Planner
import logging
import uuid
from typing import List
from zohra.services.automation.workflow_engine import Workflow, WorkflowStep

logger = logging.getLogger("zohra.automation.planner")

class TaskPlanner:
    """Compiles high-level user requests into structured executable Workflows."""
    def __init__(self):
        logger.info("Task Planner loaded.")

    def compile_plan(self, user_intent: str) -> Workflow:
        """
        Parses user intent and returns a structured Workflow.
        In a production environment, this uses an LLM to generate the step DAG.
        Here we compile structured plans for recognized intents.
        """
        intent_lower = user_intent.lower()
        steps = []
        wf_name = "Ad-hoc System Task"
        
        # 1. Trading Plan Intent
        if any(w in intent_lower for w in ["trading plan", "prepare plan", "analyze market"]):
            wf_name = "Prepare Daily Trading Plan"
            steps = [
                WorkflowStep(
                    step_id="step_1_fetch_positions",
                    action="trading.get_positions",
                    params={}
                ),
                WorkflowStep(
                    step_id="step_2_fetch_news",
                    action="research.get_economic_calendar",
                    params={"impact": "high"}
                ),
                WorkflowStep(
                    step_id="step_3_compile_pdf",
                    action="file.write_report",
                    params={},
                    depend_on=["step_1_fetch_positions", "step_2_fetch_news"]
                )
            ]
            
        # 2. Risk Management Intent
        elif any(w in intent_lower for w in ["close all", "panic", "emergency close"]):
            wf_name = "Emergency Position Liquidation"
            steps = [
                WorkflowStep(
                    step_id="step_1_close_trades",
                    action="trading.close_all_positions",
                    params={}
                ),
                WorkflowStep(
                    step_id="step_2_confirm_voice",
                    action="voice.speak",
                    params={"message": "Emergency liquidation executed. All open positions closed."},
                    depend_on=["step_1_close_trades"]
                )
            ]
            
        # 3. Default Generic Workflow
        elif "system status" in intent_lower:
            steps = [
                WorkflowStep(
                    step_id="step_1_generic",
                    action="system.status",
                    params={"input": user_intent}
                )
            ]
            
        else:
            raise ValueError("Supported workflows: prepare trading plan, system status, close all (approval required)")
        wf_id = f"wf_{uuid.uuid4().hex[:8]}"
        logger.info(f"Compiled plan for intent: '{wf_name}' with {len(steps)} steps.")
        return Workflow(workflow_id=wf_id, name=wf_name, steps=steps)
