"""
Module 13: Autonomous Decision Engine
The supreme decision-making pipeline for Zohra OS.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.mission_control.decision_engine")


class AutonomousDecisionEngine:
    """
    Ties together all specialized engines into a unified pipeline:
    Market Data -> Cross-Market Intel -> Market Regime -> Portfolio Intel ->
    Risk Analysis -> Opportunity Ranking -> Capital Allocation ->
    Strategy Selection -> Execution Approval.
    """

    def __init__(self):
        pass

    def execute_decision_cycle(self, symbol: str) -> Dict[str, Any]:
        """Runs the supreme orchestration pipeline to approve/deny active execution."""
        from zohra.mission_control.cross_market import cross_market_intel
        from zohra.mission_control.portfolio_intel import portfolio_intel
        from zohra.mission_control.risk_manager import risk_manager
        from zohra.mission_control.opportunity_ranker import opportunity_ranker
        from zohra.mission_control.capital_allocator import capital_allocator
        from zohra.mission_control.strategy_switcher import strategy_switcher

        # 1. Cross-Market Intel
        market_stats = cross_market_intel.analyze_global_market()
        risk_sentiment = market_stats["sentiment"]

        # 2. Portfolio Intel
        port_stats = portfolio_intel.evaluate_portfolio()

        # 3. Risk Analysis
        risk_stats = risk_manager.adjust_risk_parameters(
            risk_mode="moderate", market_volatility=50.0
        )

        # 4. Opportunity Ranking
        ranked_opps = opportunity_ranker.rank_opportunities()

        # Observation must not mutate strategy settings based on an assumed regime.
        strategies = strategy_switcher.strategy_states

        # 7. Execution Approval Check
        from zohra.intelligence.decision_pipeline import decision_pipeline
        recorded = decision_pipeline.get_all_decisions().get(symbol, {})
        approved = bool(recorded.get("approved")) and market_stats.get("status") == "success" and port_stats.get("status") == "success"
        reason = "Recorded pipeline decision approved; execution still requires broker authorization." if approved else "No approved pipeline decision with available market and portfolio data."

        if risk_sentiment == "RISK_OFF" and symbol == "BTCUSDT":
            approved = False
            reason = "Denied: High risk asset exposure restricted during RISK_OFF regime."

        decision = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "approved": approved,
            "reason": reason,
            "pipeline_context": {
                "risk_sentiment": risk_sentiment,
                "risk_index": market_stats["risk_index"],
                "portfolio_score": port_stats["unified_portfolio_score"],
                "risk_multiplier": risk_stats["risk_multiplier"],
                "active_strategies": [name for name, state in strategies.items() if state == "active"]
            }
        }

        # Emit decision event
        self._publish_decision_event(decision)

        return decision

    @staticmethod
    def _publish_decision_event(decision: Dict):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(event_bus.publish("decision.cycle", decision))
        except RuntimeError:
            pass


# Singleton instance
decision_engine = AutonomousDecisionEngine()
