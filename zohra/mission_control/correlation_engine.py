"""
Module 8: Cross-Asset Correlation Engine
Builds rolling asset correlation matrices.
"""

import logging
from typing import Dict

logger = logging.getLogger("zohra.mission_control.correlation_engine")


class CrossAssetCorrelationEngine:
    """
    Computes rolling correlation parameters across crypto, forex, metals, and equities.
    Prevents duplicate risk exposure to highly correlated assets.
    """

    def __init__(self):
        pass

    def compute_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """Calculates current rolling correlation matrix values."""
        from zohra.intelligence.cross_market import cross_market_engine
        import math

        prices = cross_market_engine._fetch_live_prices()
        if len(prices) < 2:
            return {}
        matrix = cross_market_engine._compute_live_correlations(prices)
        return {row: {column: value for column, value in values.items() if math.isfinite(value)}
                for row, values in matrix.items()}


# Singleton instance
correlation_engine = CrossAssetCorrelationEngine()
