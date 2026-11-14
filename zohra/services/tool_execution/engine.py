from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

from zohra.event_bus import event_bus
from zohra.security.permissions import PermissionTier
from zohra.services.tool_execution.models import ToolCall
from zohra.services.tool_execution.registry import ToolRegistry, CapabilityState

logger = logging.getLogger("zohra.tool_execution")


@dataclass
class ToolExecutionResult:
    tool_call_id: str
    status: str
    result: Any = None
    error: Optional[str] = None
    side_effects: list = field(default_factory=list)
    elapsed_ms: float = 0.0
    tool_id: str = ""
    verified: bool = False
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "side_effects": self.side_effects,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "tool_id": self.tool_id,
            "verified": self.verified,
            "error_code": self.error_code,
        }


class ToolPermissionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_CONFIRMATION = "pending_confirmation"


@dataclass(frozen=True)
class ToolPermissionDecision:
    status: ToolPermissionStatus
    configured_tier: PermissionTier
    required_tier: PermissionTier
    reason: str

    @property
    def approved(self) -> bool:
        return self.status == ToolPermissionStatus.APPROVED


def compute_rubric_tier(call: ToolCall) -> PermissionTier:
    from zohra.services.tool_execution.models import WindowsToolCall
    if not isinstance(call, WindowsToolCall):
        return call.permission_tier_required

    # 1. Reversibility
    if not call.reversible:
        score_1 = PermissionTier.IRREVERSIBLE_CONFIRM  # 3
    elif call.params.get("costly_or_slow", False):
        score_1 = PermissionTier.REVERSIBLE_CONFIRM  # 2
    else:
        score_1 = PermissionTier.REVERSIBLE_NO_CONFIRM  # 1

    # 2. Affects unnamed data
    if call.affects_unnamed_files:
        if call.params.get("broad_unnamed_effect", False):
            score_2 = PermissionTier.IRREVERSIBLE_CONFIRM  # 3
        else:
            score_2 = PermissionTier.REVERSIBLE_CONFIRM  # 2
    else:
        score_2 = PermissionTier.REVERSIBLE_NO_CONFIRM  # 1

    # 3. Real harm
    if call.requires_elevation or call.tool_id in ("file_operation.secure_shredder", "os_control.remote_desktop") or (call.tool_id == "os_control.task_manager" and call.action == "kill"):
        score_3 = PermissionTier.IRREVERSIBLE_CONFIRM  # 3
    elif call.tool_id in ("file_operation.delete_file", "file_operation.empty_recycle_bin", "file_operation.bulk_rename", "file_operation.folder_sync", "file_operation.cloud_backup", "os_control.logout_user"):
        score_3 = PermissionTier.REVERSIBLE_CONFIRM  # 2
    else:
        score_3 = PermissionTier.REVERSIBLE_NO_CONFIRM  # 1

    # Display controls, screen/file writes and window actions are not read-only.
    safe_read_tools = {"os_control.sys_info", "os_control.temp_monitor",
                       "file_operation.folder_size_analyzer", "file_operation.file_search"}
    if call.tool_id in safe_read_tools or (call.tool_id == "os_control.notification_manager" and call.action == "read") or (call.tool_id == "os_control.task_manager" and call.action == "view"):
        return PermissionTier.READ_ONLY

    computed = PermissionTier(max(int(score_1), int(score_2), int(score_3)))
    return computed


class PermissionPolicy:
    def __init__(self, capability_tiers: Dict[str, int] = None):
        if capability_tiers is None:
            raw = os.getenv("ZOHRA_PERMISSION_TIERS", "{}")
            try:
                capability_tiers = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                capability_tiers = {}
            if not isinstance(capability_tiers, dict):
                capability_tiers = {}
        self.capability_tiers = {
            str(capability): int(tier)
            for capability, tier in (capability_tiers or {}).items()
        }

    def configured_tier_for(self, capability: str) -> PermissionTier:
        configured = self.capability_tiers.get(capability, 0)
        return PermissionTier(configured)

    def allows(self, call: ToolCall) -> bool:
        return self.configured_tier_for(call.capability) >= call.permission_tier_required

    def check_permission(self, call: ToolCall, requires_confirmation: bool = False) -> ToolPermissionDecision:
        from zohra.services.tool_execution.models import WindowsToolCall
        if isinstance(call, WindowsToolCall):
            call.permission_tier_required = PermissionTier(max(int(call.permission_tier_required), int(compute_rubric_tier(call))))

        configured = self.configured_tier_for(call.capability)
        if call.permission_tier_required > configured:
            return ToolPermissionDecision(
                status=ToolPermissionStatus.REJECTED,
                configured_tier=configured,
                required_tier=call.permission_tier_required,
                reason=(
                    f"Permission tier {int(call.permission_tier_required)} required for "
                    f"'{call.capability}', configured tier is {int(configured)}."
                ),
            )
        if call.permission_tier_required > PermissionTier.READ_ONLY:
            return ToolPermissionDecision(
                status=ToolPermissionStatus.PENDING_CONFIRMATION,
                configured_tier=configured,
                required_tier=call.permission_tier_required,
                reason="Action requires explicit confirmation.",
            )
        return ToolPermissionDecision(
            status=ToolPermissionStatus.APPROVED,
            configured_tier=configured,
            required_tier=call.permission_tier_required,
            reason="Permission approved.",
        )


class ToolExecutionEngine:
    def __init__(self, registry: ToolRegistry = None, permission_policy: PermissionPolicy = None, store=None):
        self.registry = registry or ToolRegistry()
        self.permission_policy = permission_policy or PermissionPolicy()
        self.store = store

    async def execute(self, call: ToolCall, require_confirmation: bool = False) -> ToolExecutionResult:
        started = time.perf_counter()
        result = ToolExecutionResult(call.tool_call_id, "failed", tool_id=call.tool_id)
        try:
            definition = self.registry.definition(call.tool_id)
            if definition is None:
                raise PermissionError("UNVERIFIED_TOOL: This legacy handler has no validated contract. No action was executed.")
            state, reason = definition.availability()
            if state != CapabilityState.AVAILABLE:
                raise PermissionError(f"TOOL_UNAVAILABLE: {state.value}: {reason}")
            if self.store and not self.store.enabled(call.tool_id):
                raise PermissionError("TOOL_DISABLED: Owner revoked this capability")
            params = definition.input_model.model_validate(call.params).model_dump()
            # The registry, not model-supplied ToolCall fields, owns the policy.
            call.permission_tier_required = PermissionTier(definition.risk_level)
            call.timeout_sec = definition.timeout_sec
            call.reversible = definition.reversible
        except Exception as exc:
            from zohra.services.chat.assistant_tools import redact_secrets
            result.error = redact_secrets(f"{type(exc).__name__}: {exc}")
            result.error_code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "VALIDATION_ERROR" if isinstance(exc, ValueError) else "UNKNOWN_TOOL"
            result.elapsed_ms = (time.perf_counter() - started) * 1000
            await self._publish_result(call, result, failed=True)
            return result

        permission_decision = self.permission_policy.check_permission(
            call,
            requires_confirmation=require_confirmation,
        )
        if permission_decision.status == ToolPermissionStatus.REJECTED:
            result = ToolExecutionResult(
                tool_call_id=call.tool_call_id,
                status="rejected",
                error=permission_decision.reason,
                tool_id=call.tool_id, error_code="PERMISSION_DENIED",
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
            await self._publish_result(call, result, failed=True)
            return result

        if definition.confirmation_required and not definition.confirmation_bridge:
            result = ToolExecutionResult(
                tool_call_id=call.tool_call_id,
                status="requires_confirmation",
                result={"reason": "Use the action-specific assistant confirmation gate. A caller flag cannot authorize execution."},
                tool_id=call.tool_id,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
            await self._publish_result(call, result)
            return result

        try:
            if getattr(call, "requires_elevation", False):
                raise PermissionError("Strong Windows authentication is not integrated; elevation is denied")
            handler = self.registry.get(call.tool_id)
            if handler is None:
                raise NotImplementedError("No execution adapter is registered")
            if self.store and not self.store.enabled(call.tool_id):
                raise PermissionError("TOOL_DISABLED: Owner revoked this capability")
            outcome = await asyncio.wait_for(self._invoke(handler, params), timeout=call.timeout_sec)
            if not isinstance(outcome, dict):
                raise ValueError("Tool output must be a structured object")
            if outcome.get("error") or outcome.get("status") in {"failed", "error", "blocked", "rejected"}:
                raise RuntimeError(str(outcome.get("error") or outcome))
            definition.output_model.model_validate(outcome)
            pending = outcome.get("status") == "pending_confirmation"
            if definition.confirmation_bridge and not pending:
                raise PermissionError("A confirmation bridge may only create an approval preview")
            verified = False
            if not pending:
                if definition.verification is None:
                    raise RuntimeError("VERIFICATION_FAILED: No result verifier registered")
                verified = bool(await self._invoke(definition.verification, {"result": outcome}))
                if not verified:
                    raise RuntimeError("VERIFICATION_FAILED: Result failed its declared checks")
            result = ToolExecutionResult(
                tool_call_id=call.tool_call_id,
                status="requires_confirmation" if pending else "completed",
                result=outcome,
                tool_id=call.tool_id, verified=verified,
                side_effects=outcome.get("side_effects", []) if isinstance(outcome, dict) else [],
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
            await self._publish_result(call, result)
            return result
        except Exception as exc:
            from zohra.services.chat.assistant_tools import redact_secrets
            result = ToolExecutionResult(
                tool_call_id=call.tool_call_id,
                status="failed",
                error=redact_secrets(f"{type(exc).__name__}: {exc}"),
                tool_id=call.tool_id,
                error_code="TIMEOUT" if isinstance(exc, TimeoutError) else "EXECUTION_FAILED",
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
            await self._publish_result(call, result, failed=True)
            return result

    async def _invoke(self, handler: Callable, params: Dict[str, Any]) -> Any:
        if handler is None:
            return None
        if inspect.iscoroutinefunction(handler):
            return await handler(**params)
        return await asyncio.to_thread(handler, **params)

    async def _publish_result(self, call: ToolCall, result: ToolExecutionResult, failed: bool = False) -> None:
        event_type = "agent.task.failed" if failed else "agent.task.pending_confirmation" if result.status == "requires_confirmation" else "agent.task.completed"
        try:
            definition = self.registry.definition(call.tool_id)
        except KeyError:
            definition = None
        event_result = result.to_dict()
        if definition is not None and definition.private_output:
            event_result["result"] = {"redacted": True} if result.result is not None else None
            event_result["error"] = "Private tool error" if result.error else None
        await event_bus.publish(event_type, {
            "task_id": call.tool_call_id,
            "result": event_result,
            "side_effects": result.side_effects,
        })
        self._audit(call, result)
        if self.store:
            self.store.record(call.requesting_agent, call.tool_id, result.status, result.elapsed_ms,
                              {"code": result.error_code, "message": result.error} if result.error else None, result.verified)

    def _audit(self, call: ToolCall, result: ToolExecutionResult) -> None:
        logger.info(
            "ToolCall audit | id=%s agent=%s tool=%s action=%s status=%s",
            call.tool_call_id,
            call.requesting_agent,
            call.tool_id,
            call.action,
            result.status,
        )


tool_execution_engine = ToolExecutionEngine()
ToolExecutor = ToolExecutionEngine
