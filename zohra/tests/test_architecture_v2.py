import asyncio
import unittest

from zohra.core.service_discovery import ServiceConfig, StaticServiceRegistry, load_services
from zohra.event_bus import EventBus
from zohra.security.permissions import PermissionTier
from zohra.services.tool_execution.engine import PermissionPolicy, ToolExecutionEngine, ToolRegistry
from zohra.services.tool_execution.models import ToolCall
from zohra.services.tool_execution.registry import ToolDefinition
from pydantic import BaseModel, ConfigDict


class FileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    content: str


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str


class TestVolume2Architecture(unittest.TestCase):
    def test_static_services_config_loads_required_topology(self):
        services = load_services()
        self.assertIn("core", services)
        self.assertIn("trading", services)
        self.assertIn("sandbox", services)
        self.assertIn("voice", services)
        self.assertEqual(services["trading"].health_path, "/healthz")

    def test_readiness_marks_required_service_degraded_after_health_misses(self):
        registry = StaticServiceRegistry({
            "trading": ServiceConfig(
                service_id="trading",
                name="Trading Execution Service",
                host="127.0.0.1",
                port=1,
                required=True,
            )
        })

        for _ in range(3):
            readiness = registry.readiness(timeout_sec=0.01, skip_core=False)

        self.assertEqual(readiness["status"], "degraded")
        self.assertIn("trading", readiness["degraded_required_services"])

    def test_event_bus_validates_core_event_schema(self):
        bus = EventBus()
        with self.assertRaises(ValueError):
            bus.create_envelope("agent.task.requested", {"task_id": "missing-fields"})

        envelope = bus.create_envelope("agent.task.requested", {
            "agent_id": "PlannerAgent",
            "task_id": "task_1",
            "action": "noop",
            "params": {},
            "permission_tier": 0,
        })
        self.assertEqual(envelope.sequence_id, 1)

    def test_tool_execution_rejects_insufficient_permission_tier(self):
        registry = ToolRegistry()
        registry.register("filesystem.write", lambda path, content: {"path": path}, definition=ToolDefinition(
            "filesystem.write", "Fixture write", "test", input_model=FileInput, risk_level=1, confirmation_required=True))
        engine = ToolExecutionEngine(
            registry=registry,
            permission_policy=PermissionPolicy({"filesystem": 0}),
        )
        call = ToolCall(
            tool_id="filesystem.write",
            action="write",
            params={"path": "notes.txt", "content": "hello"},
            requesting_agent="CodingAgent",
            permission_tier_required=PermissionTier.REVERSIBLE_NO_CONFIRM,
            reversible=True,
        )

        result = asyncio.run(engine.execute(call))
        self.assertEqual(result.status, "rejected")

    def test_tool_execution_runs_registered_tool_when_tier_allows(self):
        registry = ToolRegistry()
        registry.register("memory.read", lambda key: {"key": key, "value": "ok"}, definition=ToolDefinition(
            "memory.read", "Fixture read", "test", input_model=MemoryInput, verification=lambda result: result.get("value") == "ok"))
        engine = ToolExecutionEngine(
            registry=registry,
            permission_policy=PermissionPolicy({"memory": 0}),
        )
        call = ToolCall(
            tool_id="memory.read",
            action="read",
            params={"key": "x"},
            requesting_agent="MemoryAgent",
            permission_tier_required=PermissionTier.READ_ONLY,
            reversible=True,
        )

        result = asyncio.run(engine.execute(call))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.result["value"], "ok")


if __name__ == "__main__":
    unittest.main()
