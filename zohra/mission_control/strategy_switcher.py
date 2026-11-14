"""
Module 11: Autonomous Strategy Switching
Coordinates deactivating or blending strategies.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger("zohra.mission_control.strategy_switcher")


class AutonomousStrategySwitching:
    """
    Monitors strategy performance coefficients and dynamically switches
    active/inactive statuses depending on regime metrics.
    """

    def __init__(self):
        self.strategy_states = {
            "scalping_strategy": "active",
            "trend_following": "active",
            "mean_reversion": "active"
        }

    def evaluate_strategies(self, market_regime: str, recent_drawdown_pct: float) -> Dict[str, str]:
        """Toggles strategy active status based on current market characteristics."""
        if market_regime in ("high_volatility", "ranging") or recent_drawdown_pct > 5.0:
            # Shift towards mean reversion, deactivate aggressive scalping
            self.strategy_states["scalping_strategy"] = "inactive"
            self.strategy_states["mean_reversion"] = "active"
        else:
            # Active trend-following and scalping in trending market
            self.strategy_states["scalping_strategy"] = "active"
            self.strategy_states["trend_following"] = "active"

        logger.info(f"Dynamic strategies statuses updated: {self.strategy_states}")
        return self.strategy_states

    def toggle_strategy(self, name: str, active: bool) -> bool:
        """Explicit strategy override."""
        if name in self.strategy_states:
            self.strategy_states[name] = "active" if active else "inactive"
            return True
        return False


# Singleton instance
strategy_switcher = AutonomousStrategySwitching()
