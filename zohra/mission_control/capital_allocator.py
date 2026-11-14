"""
Module 10: Autonomous Capital Allocation
Calculates dynamic capital distribution rules across broker gateways.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("zohra.mission_control.capital_allocator")


class AutonomousCapitalAllocation:
    """
    Distributes equity limits dynamically across multi-market engines based on
    confidence parameters, recent performance metrics, and drawdown metrics.
    """

    def __init__(self):
        pass

    def allocate_capital(self, portfolio_health: Dict[str, Any], market_regime: str) -> Dict[str, float]:
        """Calculates dynamic percentage allocations."""
        # Baseline distributions
        allocations = {
            "mt5": 40.0,
            "dhan": 30.0,
            "coindcx": 20.0,
            "cash": 10.0
        }

        # Shift target allocations depending on market regime
        if market_regime in ("high_volatility", "regime_breakout"):
            allocations["cash"] += 10.0
            allocations["coindcx"] -= 10.0
        elif market_regime == "strong_trend":
            allocations["coindcx"] += 10.0
            allocations["cash"] -= 10.0

        logger.info(f"Autonomous capital allocations adjusted: {allocations}")
        return allocations


# Singleton instance
capital_allocator = AutonomousCapitalAllocation()
