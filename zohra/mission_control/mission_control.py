"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — TRADING MISSION CONTROL                         ║
║   Supreme Intelligence, Capital Rotation & Multi-Broker Orchestrator  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from zohra.event_bus import event_bus
from zohra.config.settings import settings

from zohra.mission_control.cross_market import cross_market_intel
from zohra.mission_control.portfolio_intel import portfolio_intel
from zohra.mission_control.capital_rotation import capital_rotation_engine
from zohra.mission_control.opportunity_ranker import opportunity_ranker
from zohra.mission_control.correlation_engine import correlation_engine
from zohra.mission_control.risk_manager import risk_manager
from zohra.mission_control.capital_allocator import capital_allocator
from zohra.mission_control.strategy_switcher import strategy_switcher
from zohra.mission_control.optimization_loop import optimization_loop
from zohra.mission_control.decision_engine import decision_engine

logger = logging.getLogger("zohra.mission_control")


class TradingMissionControl:
    """
    Central brain of the Trading Division, orchestrating cross-market intelligence,
    dynamic capital rotation weights, portfolio metrics, opportunity rankings,
    risk parameters scaling, and strategy switching hooks.
    """

    def __init__(self):
        self.risk_mode = "moderate"  # conservative / moderate / aggressive / defensive
        self.allocations = capital_rotation_engine.weights
        self.strategy_states = strategy_switcher.strategy_states

    def rotate_capital(self, target_broker: str, target_percentage: float):
        """Drives dynamic capital rotations across gateways."""
        capital_rotation_engine.rotate_capital(target_broker, target_percentage)
        self._publish_update("mission.rotation", capital_rotation_engine.weights)

    def set_risk_mode(self, mode: str):
        """Set dynamic risk parameters state."""
        if mode in ("conservative", "moderate", "aggressive", "defensive"):
            self.risk_mode = mode
            logger.info(f"🛡️ [Mission Control] Global risk mode set to: {mode.upper()}")
            risk_manager.adjust_risk_parameters(mode, 50.0)
            self._publish_update("mission.risk_mode", {"risk_mode": self.risk_mode})

    def get_ranked_opportunities(self) -> List[Dict[str, Any]]:
        """Scans all assets across Forex, Crypto, and Indian markets, ranking top trading setups."""
        return opportunity_ranker.rank_opportunities()

    def get_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """Fetch correlation matrix."""
        return correlation_engine.compute_correlation_matrix()

    def toggle_strategy(self, name: str, active: bool) -> bool:
        """Dynamically toggle strategy state."""
        ok = strategy_switcher.toggle_strategy(name, active)
        if ok:
            self._publish_update("mission.strategy_switch", {"strategy": name, "state": "active" if active else "inactive"})
        return ok

    def run_optimization(self) -> Dict[str, Any]:
        """Runs the continuous parameter sweep loop."""
        return optimization_loop.trigger_parameter_sweep()

    def run_decision_cycle(self, symbol: str) -> Dict[str, Any]:
        """Supreme decision maker execution loop."""
        return decision_engine.execute_decision_cycle(symbol)

    def get_status_summary(self) -> Dict[str, Any]:
        """Aggregate system state parameters for Mission Control HUD."""
        return {
            "risk_mode": self.risk_mode,
            "allocations": capital_rotation_engine.weights,
            "strategies": strategy_switcher.strategy_states,
            "ranked_opportunities": self.get_ranked_opportunities()[:5],
            "correlation_matrix": self.get_correlation_matrix()
        }

    @staticmethod
    def _publish_update(event_type: str, data: Any):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(event_bus.publish(event_type, data))
        except RuntimeError:
            pass


# Singleton
mission_control = TradingMissionControl()
