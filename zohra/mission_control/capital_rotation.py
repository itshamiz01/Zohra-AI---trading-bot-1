"""
Module 6: Capital Rotation Engine
Calculates optimal capital allocation parameters across exchanges.
"""

import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("zohra.mission_control.capital_rotation")


class CapitalRotationEngine:
    """
    Automates multi-asset rotation calculations.
    Dynamically shifts capital allocation weight targets based on regime confidence.
    """

    def __init__(self):
        self.weights = {
            "mt5": 45.0,
            "dhan": 25.0,
            "coindcx": 15.0,
            "cash": 15.0
        }

    def rotate_capital(self, target_broker: str, target_percentage: float):
        if target_broker not in self.weights or not 0 <= target_percentage <= 100:
            raise ValueError("Unknown broker or allocation outside 0-100%")
        others = [key for key in self.weights if key != target_broker]
        remainder = sum(self.weights[key] for key in others)
        for key in others:
            self.weights[key] = (100 - target_percentage) * (self.weights[key] / remainder if remainder else 1 / len(others))
        self.weights[target_broker] = target_percentage

    def compute_rotation_matrix(self, cross_market_sentiment: str, portfolio_score: float) -> Dict[str, float]:
        """Calculates shift weight requirements based on risk regimes."""
        if cross_market_sentiment == "RISK_OFF":
            # Rotate capital towards cash/metals
            self.weights["cash"] = 35.0
            self.weights["mt5"] = 35.0  # safe haven gold
            self.weights["dhan"] = 20.0
            self.weights["coindcx"] = 10.0
        elif cross_market_sentiment == "RISK_ON":
            # Shift towards equities and crypto
            self.weights["cash"] = 10.0
            self.weights["mt5"] = 40.0
            self.weights["dhan"] = 30.0
            self.weights["coindcx"] = 20.0
            
        logger.info(f"Capital allocation rotated: {self.weights}")
        return self.weights


# Singleton instance
capital_rotation_engine = CapitalRotationEngine()
