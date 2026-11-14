# ZOHRA OS — Human-In-The-Loop Approval System
import logging
import asyncio
import uuid
from typing import Dict, Any

logger = logging.getLogger("zohra.automation.approval")

class ApprovalRequest:
    def __init__(self, action: str, params: Dict[str, Any]):
        self.request_id = f"req_{uuid.uuid4().hex[:8]}"
        self.action = action
        self.params = params
        self.status = "PENDING"  # PENDING, APPROVED, DENIED
        self.future = asyncio.Future()

class ApprovalSystem:
    """Manages confirmation gates for high-risk automation actions."""
    def __init__(self):
        self.pending_requests: Dict[str, ApprovalRequest] = {}
        logger.info("Human-In-The-Loop Approval System loaded.")

    async def request_approval(self, action: str, params: Dict[str, Any]) -> bool:
        """
        Registers a high-risk action and waits for user approval.
        Blocks the execution thread until approved or denied.
        """
        request = ApprovalRequest(action, params)
        self.pending_requests[request.request_id] = request
        
        logger.warning(f"⚠️ SECURITY GATE: Action '{action}' requires owner approval. Request ID: {request.request_id}")
        
        # Broadcast the request to the UI (this is handled by the WebSocket event bus)
        # For simulation/test, we automatically approve after a brief wait if in auto-test mode,
        # otherwise we wait for the future to resolve.
        
        try:
            # Wait for user input (resolved via resolve_request endpoint)
            approved = await request.future
            if approved:
                logger.info(f"✅ Request {request.request_id} APPROVED by owner.")
                return True
            else:
                logger.error(f"❌ Request {request.request_id} DENIED by owner.")
                raise PermissionError(f"Action '{action}' was denied by the user.")
        finally:
            self.pending_requests.pop(request.request_id, None)

    def resolve_request(self, request_id: str, approved: bool):
        """Resolves a pending approval request from the UI or Voice command."""
        if request_id in self.pending_requests:
            request = self.pending_requests[request_id]
            request.status = "APPROVED" if approved else "DENIED"
            request.future.set_result(approved)
            logger.info(f"Resolved approval request {request_id}: {request.status}")
        else:
            logger.warning(f"Attempted to resolve non-existent request: {request_id}")
