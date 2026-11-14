"""
Module 7: Opportunity Ranking Engine
Scans and evaluates opportunities across markets.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger("zohra.mission_control.opportunity_ranker")


class OpportunityRankingEngine:
    """
    Standardizes trade opportunities across symbols, timeframes, and strategies
    into a sorted leaderboard using confidence levels and risk-reward ratios.
    """

    def __init__(self):
        pass

    def rank_opportunities(self) -> List[Dict[str, Any]]:
        """Scans all assets across Forex, Crypto, and Indian markets, ranking top trading setups."""
        opps = []
        try:
            from zohra.intelligence.decision_pipeline import decision_pipeline
            decisions = decision_pipeline.get_all_decisions()
            for symbol, dec in decisions.items():
                if dec.get("decision") in ("BUY", "SELL"):
                    opps.append({
                        "symbol": symbol,
                        "decision": dec["decision"],
                        "direction": dec.get("direction", "NEUTRAL"),
                        "confidence": dec.get("confidence", 50.0),
                        "reasons": dec.get("reasons", []),
                        "timestamp": dec.get("timestamp", datetime.utcnow().isoformat())
                    })
        except Exception as exc:
            logger.warning("Unable to read decision pipeline opportunities: %s", exc)

        # An empty leaderboard correctly communicates that the decision
        # pipeline has not produced a verified opportunity yet.

        return sorted(opps, key=lambda x: x["confidence"], reverse=True)


# Singleton instance
opportunity_ranker = OpportunityRankingEngine()
