# ZOHRA OS — Automation Agent (Volume 8)
import logging
from typing import Dict, Any, List

from zohra.services.tool_execution.engine import tool_execution_engine
from zohra.services.automation.windows_integration import register_all_capabilities
from zohra.services.tool_execution.models import WindowsToolCall
from zohra.security.permissions import PermissionTier

logger = logging.getLogger("zohra.agents.automation")


class AutomationAgent:
    """
    Automation Agent (V5.3, V8.1).
    Gated exactly like any other agent. Routes all Windows integration
    features through the central ToolExecutionEngine.
    """
    def __init__(self):
        # Register all OS capabilities with the tool execution engine registry
        register_all_capabilities(tool_execution_engine.registry)
        logger.info("Automation Agent initialized. Registered OS integration capabilities.")

    async def execute_os_action(
        self,
        tool_id: str,
        action: str,
        params: Dict[str, Any],
        reversible: bool = True,
        requires_elevation: bool = False,
        affects_unnamed_files: bool = False,
        dry_run_available: bool = False,
    ) -> Dict[str, Any]:
        """
        Routes an OS action through the ToolExecutionEngine.
        This ensures it passes through the rubric check and UAC confirmation prompts.
        """
        # Create a WindowsToolCall with the appropriate metadata
        call = WindowsToolCall(
            tool_id=tool_id,
            action=action,
            params=params,
            requesting_agent="automation_agent",
            permission_tier_required=PermissionTier.READ_ONLY,  # Will be adjusted by check_permission using rubric
            reversible=reversible,
            dry_run_available=dry_run_available,
            windows_api_used=tool_id,
            requires_elevation=requires_elevation,
            affects_unnamed_files=affects_unnamed_files,
        )

        result = await tool_execution_engine.execute(call, require_confirmation=True)
        if result.status == "completed":
            return {"status": "success", "result": result.result}
        elif result.status == "rejected":
            return {"status": "rejected", "error": result.error}
        elif result.status == "requires_confirmation":
            return {"status": "requires_confirmation", "result": result.result}
        else:
            return {"status": "failed", "error": result.error}


# Singleton instance
automation_agent = AutomationAgent()
