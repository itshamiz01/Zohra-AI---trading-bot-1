"""Foundation contract tests; no trading, process termination or shutdown execution."""
import asyncio
import json
import sqlite3

import pytest
from pydantic import BaseModel, ConfigDict, Field

from zohra.security.permissions import PermissionTier
from zohra.services.tool_execution.engine import ToolExecutor, PermissionPolicy
from zohra.services.tool_execution.models import ToolCall, WindowsToolCall
from zohra.services.tool_execution.registry import ToolDefinition, ToolRegistry, CapabilityState
from zohra.services.tool_execution.state import CapabilityStore
from zohra.services.tool_execution.catalog import get_registry, capability_inventory, processes, network
from zohra.services.tool_execution.queue import ToolTaskQueue


class NumberInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    amount: int = Field(ge=0, le=100)


def call(name="test.read", params=None, **kwargs):
    return ToolCall(name, "read", params or {}, "test-session", PermissionTier.READ_ONLY, True, **kwargs)


def execute(registry, request, store=None):
    return asyncio.run(ToolExecutor(registry, PermissionPolicy({"test": 3}), store).execute(request))


def test_legacy_success_placeholder_is_never_executed():
    registry = ToolRegistry()
    hit = []
    registry.register("test.legacy", lambda: hit.append(True) or {"status": "success"})
    result = execute(registry, call("test.legacy"))
    assert result.status == "failed" and "UNVERIFIED_TOOL" in result.error
    assert hit == []


@pytest.mark.parametrize("params", [{"amount": "40"}, {"amount": True}, {"amount": 101}, {"amount": -1}, {"amount": 40, "simulated_elevation_approved": True}])
def test_strict_input_contract_rejects_coercion_and_extra_authority(params):
    registry = ToolRegistry()
    registry.register("test.read", lambda amount: {"amount": amount}, definition=ToolDefinition("test.read", "read", "test", input_model=NumberInput, verification=lambda result: True))
    result = execute(registry, call(params=params))
    assert result.status == "failed" and result.error_code == "VALIDATION_ERROR"


def test_verified_read_executes_and_persists_actual_result(tmp_path):
    registry = ToolRegistry()
    registry.register("test.read", lambda amount: {"amount": amount}, definition=ToolDefinition("test.read", "read", "test", input_model=NumberInput, verification=lambda result: result["amount"] == 40))
    store = CapabilityStore(tmp_path)
    result = execute(registry, call(params={"amount": 40}), store)
    assert result.status == "completed" and result.verified and result.result == {"amount": 40}
    record = store.history("test-session")[0]
    assert record["verified"] and record["elapsed_ms"] >= 0


def test_failed_verification_is_not_completion():
    registry = ToolRegistry()
    registry.register("test.read", lambda: {"status": "success"}, definition=ToolDefinition("test.read", "read", "test", verification=lambda result: False))
    result = execute(registry, call())
    assert result.status == "failed" and not result.verified and "VERIFICATION_FAILED" in result.error


@pytest.mark.parametrize("require_confirmation", [False, True])
def test_caller_flags_and_tier_zero_cannot_authorize_mutation(require_confirmation):
    registry, hit = ToolRegistry(), []
    registry.register("test.write", lambda: hit.append(True) or {}, definition=ToolDefinition("test.write", "write", "test", risk_level=2, confirmation_required=True))
    request = call("test.write")
    result = asyncio.run(ToolExecutor(registry, PermissionPolicy({"test":3})).execute(request, require_confirmation))
    assert result.status == "requires_confirmation" and request.permission_tier_required == PermissionTier.REVERSIBLE_CONFIRM
    assert hit == []


def test_unavailable_dependency_does_not_dispatch():
    registry = ToolRegistry()
    registry.register("test.read", lambda: pytest.fail("must not dispatch"), definition=ToolDefinition("test.read", "read", "test", availability=lambda: (CapabilityState.DEPENDENCY_MISSING, "missing device")))
    result = execute(registry, call())
    assert "Dependency Missing" in result.error and "missing device" in result.error


def test_disabled_tool_fails_after_policy_read(tmp_path):
    store = CapabilityStore(tmp_path)
    with store.session() as db:
        db.execute("INSERT INTO tool_controls VALUES('test.read',0,'now')")
    registry = ToolRegistry()
    registry.register("test.read", lambda: pytest.fail("must not dispatch"), definition=ToolDefinition("test.read", "read", "test", verification=lambda result: True))
    assert "TOOL_DISABLED" in execute(registry, call(), store).error


def test_real_handler_error_is_redacted_and_recorded(tmp_path):
    def fail():
        raise ConnectionError("sensor offline password=private-pass")
    registry = ToolRegistry()
    registry.register("test.read", fail, definition=ToolDefinition("test.read", "read", "test", verification=lambda result: True))
    store = CapabilityStore(tmp_path)
    result = execute(registry, call(), store)
    assert "ConnectionError" in result.error and "sensor offline" in result.error and "private-pass" not in result.error
    assert "private-pass" not in json.dumps(store.history("test-session"))


def test_elevation_cannot_use_simulation_flag():
    registry = ToolRegistry()
    registry.register("test.read", lambda: pytest.fail("must not dispatch"), definition=ToolDefinition("test.read", "read", "test", verification=lambda result: True))
    request = WindowsToolCall("test.read", "read", {}, "test-session", PermissionTier.READ_ONLY, True, requires_elevation=True)
    result = execute(registry, request)
    assert result.status == "requires_confirmation" or "denied" in result.error


def test_confirmation_adapter_cannot_report_completed():
    registry = ToolRegistry()
    registry.register("test.write", lambda: {"status":"success"}, definition=ToolDefinition("test.write", "preview", "test", risk_level=2, confirmation_required=True, confirmation_bridge=True))
    result = execute(registry, call("test.write"))
    assert result.status == "failed" and "preview" in result.error


def test_read_timeout_is_real_not_completed():
    async def slow():
        await asyncio.sleep(1)
        return {}
    registry = ToolRegistry()
    registry.register("test.read", slow, definition=ToolDefinition("test.read", "read", "test", timeout_sec=.01, verification=lambda result: True))
    assert execute(registry, call()).error_code == "TIMEOUT"


def test_registry_contracts_and_unimplemented_blockers(monkeypatch, tmp_path):
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE", str(tmp_path))
    tools = {row["name"]:row for row in capability_inventory()}
    assert tools["system.processes"]["input_schema"]["additionalProperties"] is False
    assert tools["system.processes"]["output_schema"]["properties"]["process_count"]
    assert tools["files.create"]["confirmation_required"]
    assert tools["android.agent"]["availability"] == "Unsupported"
    assert not tools["security.configure"]["controllable"]
    assert get_registry().get("android.agent") is None


def test_native_monitoring_is_not_fixed_simulated_data():
    result = processes()
    assert result["process_count"] > 0 and any(row["pid"] > 0 for row in result["processes"])
    assert 0 <= result["ram_usage_pct"] <= 100 and result["observed_at"]
    assert isinstance(network()["interfaces"], list)


@pytest.mark.parametrize("mode", ["pending", "unverified", "write_failure"])
def test_queue_never_replays_pending_unverified_or_mutating_work(mode):
    registry, hits = ToolRegistry(), []

    def handler():
        hits.append(True)
        raise ConnectionError("test executor offline")

    if mode == "unverified":
        registry.register("test.read", handler)
    else:
        registry.register("test.read", handler, definition=ToolDefinition(
            "test.read", "write", "test", risk_level=2, confirmation_required=True,
            confirmation_bridge=mode == "write_failure"))
    queue = ToolTaskQueue(ToolExecutor(registry, PermissionPolicy({"test":3})), max_retries=3)
    result = asyncio.run(queue.submit(call()))
    assert result.status in {"failed", "requires_confirmation"}
    assert len(hits) == (1 if mode == "write_failure" else 0)
    assert queue.dead_letters == []
