"""
Module 4: Cross-Market Intelligence Engine
Tracks intermarket dynamics, global capital flows, and risk sentiments.
"""

import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("zohra.mission_control.cross_market")


class CrossMarketIntelligenceEngine:
    """
    Synthesizes indices, commodities, currencies, bonds, and VIX
    into a unified intermarket risk-sentiment index (Risk-On / Risk-Off).
    """

    def __init__(self):
        self.sentiment_state = "UNKNOWN"
        self.risk_index = None

    def analyze_global_market(self) -> Dict[str, Any]:
        """Runs rolling correlation and liquidity scans to produce risk sentiment indices."""
        from zohra.intelligence.cross_market import cross_market_engine
        prices = cross_market_engine._fetch_live_prices()
        returns = [float(series[-1] / series[-5] - 1) for symbol, series in prices.items()
                   if symbol in {"US500", "NAS100", "BTCUSDT", "ETHUSDT"}
                   and len(series) >= 5 and series[-5] > 0]
        if not returns:
            self.risk_index = None
            self.sentiment_state = "UNKNOWN"
            return {"status": "unavailable", "timestamp": datetime.utcnow().isoformat(),
                    "sentiment": "UNKNOWN", "risk_index": None, "capital_flow": {},
                    "macro_bias": "UNKNOWN", "reason": "No current risk-asset price history"}
        self.risk_index = round(max(0, min(100, 50 + sum(returns) / len(returns) * 1000)), 2)
        if self.risk_index < 40.0:
            self.sentiment_state = "RISK_OFF"
        elif self.risk_index > 65.0:
            self.sentiment_state = "RISK_ON"
        else:
            self.sentiment_state = "NEUTRAL"

        logger.debug(f"Intermarket risk index calculated: {self.risk_index} ({self.sentiment_state})")

        return {
            "status": "success",
            "method": "Price-momentum heuristic from the latest four hourly returns",
            "timestamp": datetime.utcnow().isoformat(),
            "sentiment": self.sentiment_state,
            "risk_index": self.risk_index,
            "capital_flow": {},
            "macro_bias": {"RISK_ON": "BULLISH", "RISK_OFF": "BEARISH", "NEUTRAL": "NEUTRAL"}[self.sentiment_state]
        }


# Singleton instance
cross_market_intel = CrossMarketIntelligenceEngine()
