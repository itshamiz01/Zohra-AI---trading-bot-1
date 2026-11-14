from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from zohra.services.chat.context_manager import ContextAssembly, ContextManager
from zohra.services.chat.conversation_memory import conversation_memory
from zohra.services.chat.model_router import ModelRoute, ModelRouter
from zohra.services.chat.prompt_manager import PromptManager, prompt_manager
from zohra.services.chat.vector_memory import vector_memory


@dataclass(frozen=True)
class ReasoningTurn:
    intent: str
    parameters: Dict[str, Any]
    memory_category: Optional[str]
    assembly: ContextAssembly
    route: ModelRoute
    template_id: str


class ChatReasoningOrchestrator:
    """Coordinates context assembly, prompt templating, and model routing."""

    def __init__(
        self,
        *,
        context_manager: Optional[ContextManager] = None,
        prompt_manager_: Optional[PromptManager] = None,
        model_router: Optional[ModelRouter] = None,
    ):
        self.context_manager = context_manager or ContextManager()
        self.prompt_manager = prompt_manager_ or prompt_manager
        self.model_router = model_router or ModelRouter()

    def _memory_category_for_intent(self, intent: str) -> Optional[str]:
        intent = (intent or "").upper()
        if intent == "TRADING_QUERY":
            return "trade_memory"
        if intent == "ANALYTICS_QUERY":
            return "improvement_memory"
        if intent == "LEARNING_QUERY":
            return "strategy_memory"
        if intent == "JOURNAL_QUERY":
            return "error_memory"
        if intent == "MEMORY_QUERY":
            return "general"
        return None

    def _task_kind_for_intent(self, intent: str) -> str:
        intent = (intent or "").upper()
        if intent == "TRADING_QUERY":
            return "trading"
        if intent in {"SYSTEM_QUERY", "INFRASTRUCTURE_QUERY"}:
            return "security"
        if intent == "FILE_QUERY":
            return "file_delete"
        return "general"

    def _domain_risk_for_intent(self, intent: str, parameters: Dict[str, Any]) -> str:
        intent = (intent or "").upper()
        if intent == "TRADING_QUERY":
            action = str(parameters.get("action", "")).lower()
            if action in {"close_all", "close_profitable", "modify_risk", "halt", "resume"}:
                return "critical"
            return "high"
        if intent in {"SYSTEM_QUERY", "INFRASTRUCTURE_QUERY", "FILE_QUERY"}:
            return "high"
        return "normal"

    def _permission_summary(self, intent: str, parameters: Dict[str, Any]) -> str:
        intent = (intent or "").upper()
        if intent == "TRADING_QUERY":
            action = str(parameters.get("action", "get_positions")).lower()
            if action in {"close_all", "close_profitable", "modify_risk", "halt", "resume"}:
                return "High-consequence trading control request. Treat it as permission-gated and confirm before irreversible action."
            return "Trading analysis request. Use live state only when it is explicitly available."
        if intent in {"SYSTEM_QUERY", "INFRASTRUCTURE_QUERY", "FILE_QUERY"}:
            return "Operational request. Respect destructive-action safeguards and present a clear confirmation path."
        return "General request. Stay local-first and avoid inventing facts."

    def build_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        intent: str,
        parameters: Dict[str, Any],
        recent_turns: Optional[Iterable[Dict[str, Any]]] = None,
        retrieved_memory: Optional[str] = None,
        tool_results: Optional[Iterable[Dict[str, Any]]] = None,
        active_agent: str = "conversation",
        network_available: Optional[bool] = None,
        budget_remaining_usd: Optional[float] = None,
    ) -> ReasoningTurn:
        memory_category = self._memory_category_for_intent(intent)
        if retrieved_memory is None and memory_category:
            retrieved_memory = vector_memory.query_semantic_memories(user_message, category=memory_category, limit=2)
        retrieved_memory = retrieved_memory or ""

        if recent_turns is None:
            recent_turns = conversation_memory.get_history(session_id)

        template_id = "brain.agent.trading.system_v3" if intent == "TRADING_QUERY" else "brain.agent.general.system_v3"
        template = self.prompt_manager.render_system_prompt(
            template_id,
            permission_summary=self._permission_summary(intent, parameters),
            extra_rules=[
                f"Active agent: {active_agent}.",
                "Context assembly order must remain fixed and inspectable.",
            ],
        )

        assembly = self.context_manager.build(
            system_prompt=template,
            permission_summary=self._permission_summary(intent, parameters),
            retrieved_memory=retrieved_memory,
            recent_turns=recent_turns,
            tool_results=list(tool_results or []),
            user_message=user_message,
            metadata={
                "session_id": session_id,
                "intent": intent,
                "active_agent": active_agent,
                "memory_category": memory_category,
            },
        )

        route = self.model_router.select_route(
            task_kind=self._task_kind_for_intent(intent),
            domain_risk=self._domain_risk_for_intent(intent, parameters),
            network_available=network_available,
            complexity="high" if intent == "TRADING_QUERY" else "medium",
            budget_remaining_usd=budget_remaining_usd,
        )

        return ReasoningTurn(
            intent=intent,
            parameters=parameters,
            memory_category=memory_category,
            assembly=assembly,
            route=route,
            template_id=template_id,
        )

    def build_context_snapshot(self, turn: ReasoningTurn) -> Dict[str, Any]:
        return turn.assembly.inspection_record()

    def build_openai_messages(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        return turn.assembly.to_openai_messages()

    def build_gemini_messages(self, turn: ReasoningTurn) -> List[Dict[str, Any]]:
        return turn.assembly.to_gemini_messages()

    def build_tool_interpretation_prompt(self, tool_output: str, user_request: str) -> str:
        return self.prompt_manager.render_tool_interpretation_prompt(tool_output, user_request)

    def build_reflection_prompt(self, user_request: str, assistant_reply: str) -> str:
        return self.prompt_manager.render_reflection_prompt(user_request, assistant_reply)

    def build_planning_prompt(self, user_request: str, context_snapshot: str) -> str:
        return self.prompt_manager.render_planning_prompt(user_request, context_snapshot)


reasoning_orchestrator = ChatReasoningOrchestrator()

