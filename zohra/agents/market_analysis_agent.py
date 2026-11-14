import pandas as pd
from typing import Dict, Any, Optional
from zohra.core.agent_message import AgentMessage
from zohra.core.decision_engine import decision_engine, DecisionExplanation

class MarketAnalysisAgent:
    """
    Market Analysis Agent:
    - Analyzes price structure, volume, SMC zones, momentum, and volatility.
    - Classifies market regimes and routes appropriate strategy.
    - Generates and broadcasts Trade Proposals to the News & Risk agents.
    """
    def __init__(self, min_score_threshold: int = 70):
        self.min_score_threshold = min_score_threshold

    def analyze_market(self, df_m5: pd.DataFrame, df_m15: pd.DataFrame, df_h1: pd.DataFrame, symbol: str) -> Optional[AgentMessage]:
        """
        Runs the 6-layer pipeline for market scan and generates a PROPOSAL if a setup exists.
        """
        explanation: DecisionExplanation = decision_engine.process_data(df_m5, df_m15, df_h1, symbol)
        
        # If no strategy triggered a setup, return None
        if explanation.strategy_used == "none":
            return None

        # Determine direction based on TP/SL or description
        direction = "LONG"
        if explanation.take_profit > 0 and explanation.entry_price > 0:
            if explanation.take_profit < explanation.entry_price:
                direction = "SHORT"
        elif "short" in explanation.summary_reason.lower() or "sell" in explanation.summary_reason.lower():
            direction = "SHORT"
            
        proposal_payload = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": explanation.entry_price,
            "stop_loss": explanation.stop_loss,
            "take_profit": explanation.take_profit,
            "regime": explanation.regime,
            "strategy": explanation.strategy_used,
            "confidence_score": explanation.confidence_score,
            "explanation": explanation.to_dict()
        }
        
        return AgentMessage(
            sender="MarketAnalysisAgent",
            message_type="PROPOSAL",
            payload=proposal_payload
        )
