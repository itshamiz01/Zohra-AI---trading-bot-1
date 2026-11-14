import unittest

from zohra.services.chat.context_manager import ContextManager
from zohra.services.chat.model_router import ModelRouter
from zohra.services.chat.prompt_manager import prompt_manager
from zohra.services.chat.reasoning_orchestrator import ChatReasoningOrchestrator
from zohra.services.chat.reflection_engine import reflection_engine


class TestVolume3Brain(unittest.TestCase):
    def test_context_assembly_is_deterministic_and_ordered(self):
        manager = ContextManager()
        assembly_one = manager.build(
            system_prompt="System A",
            permission_summary="Tier: read only",
            retrieved_memory="Memory block",
            recent_turns=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            tool_results=[{"name": "tool.alpha", "result": {"ok": True}}],
            user_message="What is next?",
            metadata={"intent": "GENERAL_QUERY"},
        )
        assembly_two = manager.build(
            system_prompt="System A",
            permission_summary="Tier: read only",
            retrieved_memory="Memory block",
            recent_turns=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            tool_results=[{"name": "tool.alpha", "result": {"ok": True}}],
            user_message="What is next?",
            metadata={"intent": "GENERAL_QUERY"},
        )

        self.assertEqual(assembly_one.inspection_record()["signature"], assembly_two.inspection_record()["signature"])
        self.assertEqual(
            [section["name"] for section in assembly_one.inspection_record()["sections"]],
            ["system_prompt", "permission_summary", "retrieved_memory", "recent_turns", "tool_results", "user_message"],
        )

        messages = assembly_one.to_openai_messages()
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIn("System A", messages[0]["content"])

    def test_model_router_forces_local_when_network_is_off(self):
        router = ModelRouter()
        route = router.select_route(task_kind="trading", domain_risk="critical", network_available=False)

        self.assertEqual(route.provider, "ollama")
        self.assertFalse(route.requires_network)
        self.assertIn("Network unavailable", route.reason)

    def test_prompt_manager_loads_versioned_templates(self):
        template = prompt_manager.get_template("brain.agent.trading.system_v3")

        self.assertEqual(template.version, 3)
        rendered = prompt_manager.render_system_prompt(
            "brain.agent.trading.system_v3",
            permission_summary="Tier 3 only",
            extra_rules=["Keep responses short."],
        )
        self.assertIn("Tier 3 only", rendered)
        self.assertIn("Keep responses short.", rendered)

    def test_reasoning_orchestrator_builds_stable_snapshot(self):
        orchestrator = ChatReasoningOrchestrator()
        turn_one = orchestrator.build_turn(
            session_id="session-1",
            user_message="Check risk and memory.",
            intent="TRADING_QUERY",
            parameters={"action": "get_positions"},
            recent_turns=[{"role": "user", "content": "Earlier question"}],
            retrieved_memory="Relevant memory",
            tool_results=[{"name": "tool.beta", "result": "ok"}],
            network_available=False,
        )
        turn_two = orchestrator.build_turn(
            session_id="session-1",
            user_message="Check risk and memory.",
            intent="TRADING_QUERY",
            parameters={"action": "get_positions"},
            recent_turns=[{"role": "user", "content": "Earlier question"}],
            retrieved_memory="Relevant memory",
            tool_results=[{"name": "tool.beta", "result": "ok"}],
            network_available=False,
        )

        self.assertEqual(turn_one.assembly.inspection_record()["signature"], turn_two.assembly.inspection_record()["signature"])
        self.assertEqual(turn_one.route.provider, "ollama")
        self.assertEqual(turn_one.template_id, "brain.agent.trading.system_v3")

    def test_reflection_bounds_memory_capture(self):
        self.assertTrue(reflection_engine.should_store_memory(
            "Please remember this strategy",
            "We should optimize the plan."
        ))
        self.assertFalse(reflection_engine.should_store_memory("Hello", "Hi there"))


if __name__ == "__main__":
    unittest.main()
