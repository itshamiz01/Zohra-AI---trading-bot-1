import asyncio
import unittest
import time
from typing import Dict, Any

from zohra.security.permissions import PermissionTier
from zohra.services.tool_execution.models import ToolCall
from zohra.agents.framework import (
    PermissionStatus,
    AgentPermissionPolicy,
    check_permission,
    requires_confirmation,
    write_procedural_memory,
    ScopeViolationError,
    A2AMessage,
    A2AMessageBus,
    A2ARoundTripExceeded,
    ResourceLockManager,
    LockStatus,
    PermissionEscalationManager,
    EscalationProposal,
    ConflictType,
    CompetingPlan,
    AgentConflict,
    ArbitrationAction,
    CEOAgentArbitrator,
    PlanNode,
    PlanDAG,
    MultiAgentScheduler,
)

# Mock memory store to verify procedural scope enforcement
class MockStore:
    def __init__(self):
        self.procedural = []

    def upsert_procedural_memory(self, instruction: str, derived_from: list, metadata: dict) -> str:
        self.procedural.append({"instruction": instruction, "metadata": metadata})
        return "success"


class TestMultiAgentFrameworkV5(unittest.TestCase):
    def test_permission_tier_enforcement(self):
        # Setup tool calls
        call_read = ToolCall(
            tool_id="filesystem.read",
            action="read",
            params={"path": "test.txt"},
            requesting_agent="coding_agent",
            permission_tier_required=PermissionTier.READ_ONLY,
            reversible=True,
        )
        call_write = ToolCall(
            tool_id="filesystem.write",
            action="write",
            params={"path": "test.txt", "content": "hi"},
            requesting_agent="coding_agent",
            permission_tier_required=PermissionTier.REVERSIBLE_CONFIRM,
            reversible=True,
        )

        # Policy checks
        policy = AgentPermissionPolicy(agent_capability_tiers={
            "coding_agent": {
                "filesystem": int(PermissionTier.READ_ONLY)
            }
        })
        # Mock global policy for check_permission
        from zohra.agents import framework
        old_policy = framework.agent_permission_policy
        framework.agent_permission_policy = policy

        try:
            # Read-only capability is READ_ONLY (0). required READ_ONLY (0) <= configured READ_ONLY (0) -> APPROVED
            dec1 = check_permission("coding_agent", call_read)
            self.assertEqual(dec1.status, PermissionStatus.APPROVED)

            # Write capability is REVERSIBLE_CONFIRM (2). required (2) > configured READ_ONLY (0) -> REJECTED
            dec2 = check_permission("coding_agent", call_write)
            self.assertEqual(dec2.status, PermissionStatus.REJECTED)

            # Upgrade tier
            policy.agent_capability_tiers["coding_agent"]["filesystem"] = int(PermissionTier.REVERSIBLE_CONFIRM)
            dec3 = check_permission("coding_agent", call_write)
            self.assertEqual(dec3.status, PermissionStatus.PENDING_CONFIRMATION)
        finally:
            framework.agent_permission_policy = old_policy

    def test_scoped_write_procedural_memory(self):
        store = MockStore()

        # Valid scope: starts with agent_id.
        write_procedural_memory("coding_agent", "coding_agent.verbosity", "Use concise logs", store=store)
        self.assertEqual(len(store.procedural), 1)

        # Invalid scope: doesn't start with agent_id.
        with self.assertRaises(ScopeViolationError):
            write_procedural_memory("finance_agent", "coding_agent.verbosity", "Use verbose logs", store=store)

    def test_evaluate_escalation_candidacy(self):
        manager = PermissionEscalationManager(current_tiers={
            "coding_agent": {
                "filesystem": int(PermissionTier.READ_ONLY)
            }
        })

        # Add 9 approved history items, not enough for 10 consecutive window
        for _ in range(9):
            manager.record_action("coding_agent", "filesystem", user_rejected=False, approved=True)

        proposal = manager.evaluate_escalation_candidacy("coding_agent", "filesystem")
        self.assertIsNone(proposal)

        # 10th approved item
        manager.record_action("coding_agent", "filesystem", user_rejected=False, approved=True)
        proposal = manager.evaluate_escalation_candidacy("coding_agent", "filesystem")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.proposed_tier, PermissionTier.READ_ONLY)  # remains at max(0, current - 1) which is READ_ONLY (0)

        # Now test that a single user rejection in the last 10 entries resets candidacy
        manager.record_action("coding_agent", "filesystem", user_rejected=True, approved=False)
        # Pad with 9 approvals
        for _ in range(9):
            manager.record_action("coding_agent", "filesystem", user_rejected=False, approved=True)

        proposal = manager.evaluate_escalation_candidacy("coding_agent", "filesystem")
        self.assertIsNone(proposal, "A single user rejection/fail in window must void candidacy")

    def test_resource_lock_contention_and_expiration(self):
        # Mock clock to simulate lock expiration
        current_time = 100.0
        def mock_clock():
            return current_time

        manager = ResourceLockManager(clock=mock_clock)

        # Acquire lock
        res1 = asyncio.run(manager.acquire_resource_lock("db_write", "trading_agent", max_hold_seconds=30))
        self.assertEqual(res1.status, LockStatus.ACQUIRED)

        # Contend lock -> QUEUED
        res2 = asyncio.run(manager.acquire_resource_lock("db_write", "coding_agent", max_hold_seconds=30))
        self.assertEqual(res2.status, LockStatus.QUEUED)
        self.assertEqual(res2.held_by, "trading_agent")
        self.assertEqual(manager.queue_for("db_write"), ["coding_agent"])

        # Advance clock past expiration (30s) -> Acquire lock succeeds
        current_time = 131.0
        res3 = asyncio.run(manager.acquire_resource_lock("db_write", "coding_agent", max_hold_seconds=30))
        self.assertEqual(res3.status, LockStatus.ACQUIRED)

    def test_ceo_agent_arbitration(self):
        arbitrator = CEOAgentArbitrator(threshold=0.70)

        # Non-trading resource contention conflict -> Defer to queue
        conflict_res = AgentConflict(conflict_type=ConflictType.RESOURCE_CONTENTION.value)
        decision1 = arbitrator.arbitrate(conflict_res)
        self.assertEqual(decision1.action, ArbitrationAction.DEFER_TO_LOCK_QUEUE)

        # Interpretation disagreement conflict with confidence below threshold
        plans = [
            CompetingPlan(plan_id="plan_a", confidence=0.55),
            CompetingPlan(plan_id="plan_b", confidence=0.65),
        ]
        conflict_dis = AgentConflict(
            conflict_type=ConflictType.INTERPRETATION_DISAGREEMENT.value,
            competing_plans=plans
        )
        decision2 = arbitrator.arbitrate(conflict_dis)
        self.assertEqual(decision2.action, ArbitrationAction.ASK_USER)
        self.assertEqual(len(decision2.competing_plans), 2)

        # Interpretation disagreement conflict with confidence above threshold
        plans_high = [
            CompetingPlan(plan_id="plan_a", confidence=0.55),
            CompetingPlan(plan_id="plan_b", confidence=0.85),
        ]
        conflict_high = AgentConflict(
            conflict_type=ConflictType.INTERPRETATION_DISAGREEMENT.value,
            competing_plans=plans_high
        )
        decision3 = arbitrator.arbitrate(conflict_high)
        self.assertEqual(decision3.action, ArbitrationAction.SELECT_PLAN)
        self.assertEqual(decision3.selected_plan_id, "plan_b")

    def test_plan_dag_and_delegation_scheduler(self):
        # Create DAG
        nodes = [
            PlanNode("node_1", capability="web_search", priority=10),
            PlanNode("node_2", capability="code_generation", priority=20, dependencies=["node_1"]),
            PlanNode("node_3", capability="invalid_capability", priority=5),
        ]
        dag = PlanDAG(nodes=nodes)

        scheduler = MultiAgentScheduler(concurrency_ceiling=1)

        # Initially, only node_1 and node_3 are ready (node_2 depends on node_1)
        # Node_1 has higher priority (10) than node_3 (5), but concurrency is 1.
        # Node_1 will be dispatched, Node_3 will be queued (deferred due to concurrency ceiling)
        records = scheduler.delegate_plan(dag)
        
        dispatched_node_ids = [r.node_id for r in records if r.status == "dispatched"]
        queued_node_ids = [r.node_id for r in records if r.status == "queued"]
        
        self.assertIn("node_1", dispatched_node_ids)
        self.assertIn("node_3", queued_node_ids)

        # Test fail-closed on unmapped capability
        scheduler_unmapped = MultiAgentScheduler(concurrency_ceiling=5)
        records_unmapped = scheduler_unmapped.delegate_plan(dag)
        
        unmapped_record = next(r for r in records_unmapped if r.node_id == "node_3")
        self.assertEqual(unmapped_record.status, "unmapped")
        self.assertEqual(unmapped_record.reason, "No static capability owner configured.")


if __name__ == "__main__":
    unittest.main()
