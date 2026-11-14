from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from zohra.event_bus import event_bus
from zohra.memory.lifecycle_memory import LifecycleMemoryStore, lifecycle_memory
from zohra.security.permissions import PermissionTier
from zohra.services.tool_execution.models import ToolCall


logger = logging.getLogger("zohra.agents.framework")


CAPABILITY_MAP: Dict[str, str] = {
    "goal_decomposition": "planner_agent",
    "web_search": "research_agent",
    "code_generation": "coding_agent",
    "code_refactor": "coding_agent",
    "git_operations": "coding_agent",
    "docker_management": "devops_agent",
    "ci_cd": "devops_agent",
    "vulnerability_scan": "security_agent",
    "permission_audit": "security_agent",
    "invoicing": "finance_agent",
    "expense_tracking": "finance_agent",
    "trading_proposal": "trading_agent",
    "screen_analysis": "vision_agent",
    "ocr": "vision_agent",
    "speech_io": "voice_agent",
    "file_operation": "automation_agent",
    "os_control": "automation_agent",
    "doc_generation": "documentation_agent",
    "test_execution": "qa_agent",
}

CONCURRENCY_CEILING = 4
MAX_A2A_ROUND_TRIPS = 5
CONSECUTIVE_WINDOW = 10
INTERPRETATION_CONFIDENCE_THRESHOLD = 0.70


class PermissionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_CONFIRMATION = "pending_confirmation"


@dataclass(frozen=True)
class AgentPermissionDecision:
    status: PermissionStatus
    agent_id: str
    capability: str
    configured_tier: PermissionTier
    required_tier: PermissionTier
    reason: str

    @property
    def approved(self) -> bool:
        return self.status == PermissionStatus.APPROVED


class AgentPermissionPolicy:
    def __init__(self, agent_capability_tiers: Optional[Dict[str, Dict[str, int]]] = None):
        self.agent_capability_tiers = agent_capability_tiers or {}

    def get_current_tier(self, agent_id: str, capability: str) -> PermissionTier:
        configured = self.agent_capability_tiers.get(agent_id, {}).get(capability, 0)
        return PermissionTier(configured)

    def check_permission(
        self,
        agent_id: str,
        action: ToolCall,
        requires_confirmation: bool = False,
    ) -> AgentPermissionDecision:
        agent_tier = self.get_current_tier(agent_id, action.capability)
        if action.permission_tier_required > agent_tier:
            return AgentPermissionDecision(
                status=PermissionStatus.REJECTED,
                agent_id=agent_id,
                capability=action.capability,
                configured_tier=agent_tier,
                required_tier=action.permission_tier_required,
                reason="Configured permission tier is below the action requirement.",
            )
        if action.permission_tier_required in (
            PermissionTier.REVERSIBLE_CONFIRM,
            PermissionTier.IRREVERSIBLE_CONFIRM,
        ) and requires_confirmation:
            return AgentPermissionDecision(
                status=PermissionStatus.PENDING_CONFIRMATION,
                agent_id=agent_id,
                capability=action.capability,
                configured_tier=agent_tier,
                required_tier=action.permission_tier_required,
                reason="Action requires explicit confirmation.",
            )
        return AgentPermissionDecision(
            status=PermissionStatus.APPROVED,
            agent_id=agent_id,
            capability=action.capability,
            configured_tier=agent_tier,
            required_tier=action.permission_tier_required,
            reason="Permission approved.",
        )


def requires_confirmation(action: ToolCall) -> bool:
    """Returns True if the action requires user confirmation (Tier 2 or Tier 3)."""
    return action.permission_tier_required in (
        PermissionTier.REVERSIBLE_CONFIRM,
        PermissionTier.IRREVERSIBLE_CONFIRM,
    )


def check_permission(agent_id: str, action: ToolCall) -> AgentPermissionDecision:
    """Top-level permission check conforming to Zohra AI Bible Vol 5."""
    from zohra.services.tool_execution.models import WindowsToolCall
    if isinstance(action, WindowsToolCall):
        from zohra.services.tool_execution.engine import compute_rubric_tier
        action.permission_tier_required = compute_rubric_tier(action)

    agent_tier = agent_permission_policy.get_current_tier(agent_id, action.capability)
    if action.permission_tier_required > agent_tier:
        return AgentPermissionDecision(
            status=PermissionStatus.REJECTED,
            agent_id=agent_id,
            capability=action.capability,
            configured_tier=agent_tier,
            required_tier=action.permission_tier_required,
            reason="Configured permission tier is below the action requirement.",
        )
    if action.permission_tier_required in (
        PermissionTier.REVERSIBLE_CONFIRM,
        PermissionTier.IRREVERSIBLE_CONFIRM,
    ) and requires_confirmation(action):
        return AgentPermissionDecision(
            status=PermissionStatus.PENDING_CONFIRMATION,
            agent_id=agent_id,
            capability=action.capability,
            configured_tier=agent_tier,
            required_tier=action.permission_tier_required,
            reason="Action requires explicit confirmation.",
        )
    return AgentPermissionDecision(
        status=PermissionStatus.APPROVED,
        agent_id=agent_id,
        capability=action.capability,
        configured_tier=agent_tier,
        required_tier=action.permission_tier_required,
        reason="Permission approved.",
    )




class ScopeViolationError(ValueError):
    pass


def write_procedural_memory(
    agent_id: str,
    rule_scope: str,
    rule_text: str,
    store: LifecycleMemoryStore = lifecycle_memory,
) -> str:
    if not rule_scope.startswith(f"{agent_id}."):
        raise ScopeViolationError(
            f"{agent_id} attempted to write procedural memory outside its own scope: {rule_scope}"
        )
    return store.upsert_procedural_memory(
        instruction=rule_text,
        derived_from=[],
        metadata={"rule_scope": rule_scope, "agent_id": agent_id},
    )


@dataclass(frozen=True)
class A2AMessage:
    from_agent: str
    to_agent: str
    intent: str
    payload: Dict[str, Any]
    requires_response: bool
    round_trip_number: int
    conversation_thread_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_event_payload(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "intent": self.intent,
            "payload": self.payload,
            "requires_response": self.requires_response,
            "round_trip_number": self.round_trip_number,
            "conversation_thread_id": self.conversation_thread_id,
        }


class A2ARoundTripExceeded(RuntimeError):
    pass


class A2AMessageBus:
    def __init__(self, max_round_trips: int = MAX_A2A_ROUND_TRIPS):
        self.max_round_trips = max_round_trips
        self.log: List[A2AMessage] = []

    async def send(self, message: A2AMessage) -> A2AMessage:
        if message.round_trip_number > self.max_round_trips:
            raise A2ARoundTripExceeded(
                f"A2A thread {message.conversation_thread_id} exceeded {self.max_round_trips} round trips."
            )
        self.log.append(message)
        await event_bus.publish("agent.message", message.to_event_payload(), source=message.from_agent)
        return message


class LockStatus(str, Enum):
    ACQUIRED = "acquired"
    QUEUED = "queued"


@dataclass(frozen=True)
class LockResult:
    status: LockStatus
    resource_id: str
    requesting_agent: str
    held_by: Optional[str] = None


class ResourceLockManager:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._locks: Dict[str, Dict[str, Any]] = {}
        self._queues: Dict[str, List[str]] = {}

    def _expire_if_needed(self, resource_id: str) -> None:
        lock = self._locks.get(resource_id)
        if lock and lock["expires_at"] <= self.clock():
            del self._locks[resource_id]

    async def acquire_resource_lock(
        self,
        resource_id: str,
        requesting_agent: str,
        max_hold_seconds: int = 30,
    ) -> LockResult:
        self._expire_if_needed(resource_id)
        if resource_id not in self._locks:
            self._locks[resource_id] = {
                "holder": requesting_agent,
                "expires_at": self.clock() + max_hold_seconds,
            }
            return LockResult(LockStatus.ACQUIRED, resource_id, requesting_agent)

        holder = self._locks[resource_id]["holder"]
        self._queues.setdefault(resource_id, []).append(requesting_agent)
        await event_bus.publish(
            "resource.lock.contended",
            {"resource_id": resource_id, "held_by": holder, "waiting": requesting_agent},
            source=requesting_agent,
        )
        return LockResult(LockStatus.QUEUED, resource_id, requesting_agent, held_by=holder)

    def release_resource_lock(self, resource_id: str, releasing_agent: str) -> Optional[LockResult]:
        self._expire_if_needed(resource_id)
        lock = self._locks.get(resource_id)
        if not lock or lock["holder"] != releasing_agent:
            return None
        del self._locks[resource_id]
        queue = self._queues.get(resource_id, [])
        if not queue:
            return None
        next_agent = queue.pop(0)
        self._locks[resource_id] = {"holder": next_agent, "expires_at": self.clock() + 30}
        return LockResult(LockStatus.ACQUIRED, resource_id, next_agent)

    def queue_for(self, resource_id: str) -> List[str]:
        return list(self._queues.get(resource_id, []))


@dataclass(frozen=True)
class PermissionActionHistory:
    agent_id: str
    action_type: str
    user_rejected: bool
    approved: bool = True
    recorded_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class EscalationProposal:
    agent_id: str
    action_type: str
    current_tier: PermissionTier
    proposed_tier: PermissionTier
    evidence_count: int
    proposal_id: str = field(default_factory=lambda: f"esc_{uuid.uuid4().hex[:12]}")


def surface_escalation_offer_to_user(proposal: EscalationProposal) -> None:
    """Surfaces an escalation offer to the user (UI / logs / events)."""
    logger.info(
        "escalation.proposal.offered | id=%s agent=%s action=%s proposed_tier=%s",
        proposal.proposal_id,
        proposal.agent_id,
        proposal.action_type,
        int(proposal.proposed_tier),
    )


class PermissionEscalationManager:
    def __init__(
        self,
        current_tiers: Optional[Dict[str, Dict[str, int]]] = None,
        consecutive_window: int = CONSECUTIVE_WINDOW,
    ):
        self.current_tiers = current_tiers or {}
        self.consecutive_window = consecutive_window
        self.history: List[PermissionActionHistory] = []
        self.accepted_history: List[EscalationProposal] = []
        self.declined_offers: List[EscalationProposal] = []

    def record_action(
        self,
        agent_id: str,
        action_type: str,
        user_rejected: bool = False,
        approved: bool = True,
    ) -> None:
        self.history.append(PermissionActionHistory(agent_id, action_type, user_rejected, approved))

    def get_current_tier(self, agent_id: str, action_type: str) -> PermissionTier:
        return PermissionTier(self.current_tiers.get(agent_id, {}).get(action_type, 0))

    def evaluate_escalation_candidacy(self, agent_id: str, action_type: str) -> Optional[EscalationProposal]:
        # Get the last CONSECUTIVE_WINDOW items for this specific agent and action type
        matching = [
            item for item in self.history
            if item.agent_id == agent_id and item.action_type == action_type
        ][-self.consecutive_window:]

        if len(matching) < self.consecutive_window:
            return None

        # A single rejection or unapproved item in the window resets candidacy
        if any(item.user_rejected or not item.approved for item in matching):
            return None

        current = self.get_current_tier(agent_id, action_type)
        proposed = PermissionTier(max(0, int(current) - 1))
        proposal = EscalationProposal(
            agent_id=agent_id,
            action_type=action_type,
            current_tier=current,
            proposed_tier=proposed,
            evidence_count=len(matching),
        )
        surface_escalation_offer_to_user(proposal)
        return proposal


    def accept_offer(self, proposal: EscalationProposal) -> None:
        self.current_tiers.setdefault(proposal.agent_id, {})[proposal.action_type] = int(proposal.proposed_tier)
        self.accepted_history.append(proposal)

    def decline_offer(self, proposal: EscalationProposal) -> None:
        self.declined_offers.append(proposal)


class ConflictType(str, Enum):
    RESOURCE_CONTENTION = "resource_contention"
    INTERPRETATION_DISAGREEMENT = "interpretation_disagreement"


@dataclass(frozen=True)
class CompetingPlan:
    plan_id: str
    confidence: float
    summary: str = ""


@dataclass(frozen=True)
class AgentConflict:
    conflict_type: str
    competing_plans: Sequence[CompetingPlan] = field(default_factory=list)


class ArbitrationAction(str, Enum):
    DEFER_TO_LOCK_QUEUE = "defer_to_lock_queue"
    SELECT_PLAN = "select_plan"
    ASK_USER = "ask_user"


@dataclass(frozen=True)
class ArbitrationDecision:
    action: ArbitrationAction
    selected_plan_id: Optional[str] = None
    competing_plans: Sequence[CompetingPlan] = field(default_factory=list)


class UnhandledConflictType(RuntimeError):
    pass


class CEOAgentArbitrator:
    def __init__(self, threshold: float = INTERPRETATION_CONFIDENCE_THRESHOLD):
        self.threshold = threshold

    def arbitrate(self, conflict: AgentConflict) -> ArbitrationDecision:
        if conflict.conflict_type == ConflictType.RESOURCE_CONTENTION.value:
            return ArbitrationDecision(ArbitrationAction.DEFER_TO_LOCK_QUEUE)

        if conflict.conflict_type == ConflictType.INTERPRETATION_DISAGREEMENT.value:
            if not conflict.competing_plans:
                return ArbitrationDecision(ArbitrationAction.ASK_USER, competing_plans=[])
            best = max(conflict.competing_plans, key=lambda plan: plan.confidence)
            if best.confidence > self.threshold:
                return ArbitrationDecision(ArbitrationAction.SELECT_PLAN, selected_plan_id=best.plan_id)
            return ArbitrationDecision(
                ArbitrationAction.ASK_USER,
                competing_plans=list(conflict.competing_plans),
            )

        raise UnhandledConflictType(conflict.conflict_type)


@dataclass(frozen=True)
class PlanNode:
    node_id: str
    capability: str
    priority: int = 0
    dependencies: Sequence[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanDAG:
    nodes: Sequence[PlanNode]
    completed_node_ids: set = field(default_factory=set)

    def ready_nodes(self) -> List[PlanNode]:
        return [
            node for node in self.nodes
            if node.node_id not in self.completed_node_ids
            and all(dep in self.completed_node_ids for dep in node.dependencies)
        ]


@dataclass(frozen=True)
class DelegationRecord:
    node_id: str
    capability: str
    status: str
    agent_id: Optional[str] = None
    reason: str = ""


def escalate_unmapped_capability(node: PlanNode) -> None:
    """Fails closed by logging and signaling an unmapped capability conflict that the user must resolve."""
    logger.error(
        f"🚨 CAPABILITY DELEGATION FAIL-CLOSED: No static capability owner configured "
        f"for capability '{node.capability}' required by node '{node.node_id}'."
    )


class MultiAgentScheduler:
    def __init__(
        self,
        capability_map: Optional[Dict[str, str]] = None,
        concurrency_ceiling: int = CONCURRENCY_CEILING,
    ):
        self.capability_map = capability_map or dict(CAPABILITY_MAP)
        self.concurrency_ceiling = concurrency_ceiling
        self.active_agent_count = 0
        self.deferred_nodes: List[PlanNode] = []
        self.unmapped_nodes: List[PlanNode] = []
        self.dispatched: List[DelegationRecord] = []

    def delegate_plan(self, dag: PlanDAG) -> List[DelegationRecord]:
        records: List[DelegationRecord] = []
        ready_nodes = sorted(dag.ready_nodes(), key=lambda node: node.priority, reverse=True)
        active_count = self.active_agent_count

        for node in ready_nodes:
            if active_count >= self.concurrency_ceiling:
                self.deferred_nodes.append(node)
                record = DelegationRecord(
                    node_id=node.node_id,
                    capability=node.capability,
                    status="queued",
                    reason="Concurrency ceiling reached.",
                )
                records.append(record)
                continue

            agent_id = self.capability_map.get(node.capability)
            if agent_id is None:
                self.unmapped_nodes.append(node)
                escalate_unmapped_capability(node)
                record = DelegationRecord(
                    node_id=node.node_id,
                    capability=node.capability,
                    status="unmapped",
                    reason="No static capability owner configured.",
                )
                records.append(record)
                continue

            record = self.dispatch_to_agent(agent_id, node)
            records.append(record)
            active_count += 1

        self.active_agent_count = active_count
        return records

    def dispatch_to_agent(self, agent_id: str, node: PlanNode) -> DelegationRecord:
        record = DelegationRecord(
            node_id=node.node_id,
            capability=node.capability,
            status="dispatched",
            agent_id=agent_id,
        )
        self.dispatched.append(record)
        return record

    def complete_agent_slot(self) -> None:
        self.active_agent_count = max(0, self.active_agent_count - 1)


agent_permission_policy = AgentPermissionPolicy()
a2a_message_bus = A2AMessageBus()
resource_lock_manager = ResourceLockManager()
permission_escalation_manager = PermissionEscalationManager()
ceo_arbitrator = CEOAgentArbitrator()
multi_agent_scheduler = MultiAgentScheduler()

