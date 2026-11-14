from datetime import datetime
from typing import Dict, Any, List
from zohra.core.agent_message import AgentMessage
from zohra.brokers.mt5_broker import mt5_broker
from zohra.config.settings import MAGIC_SMC, MAGIC_SCALP
from zohra.core.enums import StrategyName
from zohra.agents.news_agent import NewsAgent
from zohra.agents.risk_agent import RiskAgent
from zohra.agents.memory_agent import MemoryAgent
from zohra.security.permissions import TradingPermissionGateway, trading_permission_gateway

class ExecutionAgent:
    """
    Execution Agent:
    - Oversees MetaTrader 5 trade placements, exits, and modifications.
    - Coordinates consensus voting loop across News & Risk agents.
    - Logs results to the database via Memory Agent.
    """
    def __init__(self, news_agent: NewsAgent, risk_agent: RiskAgent, memory_agent: MemoryAgent,
                 min_score_threshold: int = 70, permission_gateway: TradingPermissionGateway = None,
                 broker=None):
        self.news_agent = news_agent
        self.risk_agent = risk_agent
        self.memory_agent = memory_agent
        self.min_score_threshold = min_score_threshold
        self.permission_gateway = permission_gateway or trading_permission_gateway
        self.broker = broker or mt5_broker

    def process_consensus_voting(self, proposal_msg: AgentMessage) -> Dict[str, Any]:
        """
        Runs the multi-agent consensus voting loop.
        Returns execution results.
        """
        payload = proposal_msg.payload
        symbol = payload.get("symbol")
        direction = payload.get("direction")
        score = payload.get("confidence_score", 0)
        entry = payload.get("entry_price", 0.0)
        sl = payload.get("stop_loss", 0.0)
        tp = payload.get("take_profit", 0.0)
        strategy = payload.get("strategy")
        
        # 1. Dispatch proposal to News and Risk agents to get votes
        news_vote_msg = self.news_agent.evaluate_proposal(proposal_msg)
        risk_vote_msg = self.risk_agent.evaluate_proposal(proposal_msg)
        
        news_vote = news_vote_msg.payload.get("vote")
        news_reason = news_vote_msg.payload.get("reason")
        
        risk_vote = risk_vote_msg.payload.get("vote")
        risk_lots = risk_vote_msg.payload.get("lots", 0.0)
        risk_reason = risk_vote_msg.payload.get("reason")

        # 2. Check voting rules
        is_approved = (news_vote == "APPROVE" and risk_vote == "APPROVE")
        has_veto = (news_vote == "VETO" or risk_vote == "VETO")
        score_passed = (score >= self.min_score_threshold)
        
        consensus_status = "VETOED"
        if has_veto:
            consensus_status = "VETOED"
            rejection_reason = f"Vetoed. News: {news_reason} | Risk: {risk_reason}"
        elif not score_passed:
            consensus_status = "VETOED"
            rejection_reason = f"Consensus score {score} is below threshold {self.min_score_threshold}."
        elif not is_approved:
            consensus_status = "VETOED"
            rejection_reason = f"Consensus not reached. News: {news_vote} | Risk: {risk_vote}"
        else:
            consensus_status = "APPROVED"
            rejection_reason = ""

        execution_ticket = None
        trade_id = None
        permission = None
        
        # 3. Action Execution if Approved
        if consensus_status == "APPROVED":
            magic_num = MAGIC_SMC
            if strategy == StrategyName.BREAKOUT.value:
                magic_num = MAGIC_SCALP
                
            grade = "B"
            if score >= 95:
                grade = "A+"
            elif score >= 85:
                grade = "A"
                
            permission = self.permission_gateway.authorize_trade_execution({
                "symbol": symbol,
                "direction": direction,
                "lots": risk_lots,
                "broker": payload.get("broker", "mt5"),
                "risk_approved": risk_vote == "APPROVE",
                "consensus_status": consensus_status,
                "authorization_token": payload.get("authorization_token", ""),
            })
            result = None
            if not permission.approved:
                consensus_status = "VETOED"
                rejection_reason = permission.reason
            else:
                result = self.broker.open_trade(
                    symbol=symbol,
                    direction=direction,
                    lots=risk_lots,
                    stop_loss=sl,
                    take_profit=tp,
                    magic=magic_num,
                    comment=f"DIE_{grade}_{score}"
                )
            
            if result and result.get("ticket"):
                execution_ticket = result["ticket"]
                trade_id = f"DIE_{symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                
                # Structure the open trade dictionary for the database
                explanation = payload.get("explanation", {})
                scores_breakdown = explanation.get("scores_breakdown", {})
                
                trade_dict = {
                    "trade_id": trade_id,
                    "mt5_ticket": execution_ticket,
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": entry,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "position_size_lots": risk_lots,
                    "risk_usd": float(risk_lots * abs(entry - sl) * 100_000),
                    "confidence_score": score,
                    "quality_grade": grade,
                    "session": explanation.get("session", "overlap"),
                    "market_regime": payload.get("regime"),
                    "strategy_used": strategy,
                    "reason_for_entry": explanation.get("summary_reason", "Consensus Approved"),
                    "score_structure": int(scores_breakdown.get("structure", 0)),
                    "score_liquidity": int(scores_breakdown.get("volume", 0)),
                    "score_smc": int(scores_breakdown.get("smc", 0)),
                    "score_trend": int(scores_breakdown.get("correlation", 0)),
                    "score_momentum": int(scores_breakdown.get("momentum", 0)),
                    "score_volatility": int(scores_breakdown.get("volatility", 0)),
                    "score_pullback": int(scores_breakdown.get("session", 0)),
                    "news_status": 0 if news_vote == "APPROVE" else 1
                }
                
                self.memory_agent.log_trade(trade_dict)
            elif permission and not permission.approved:
                # Preserve the permission-gate rationale in the decision log.
                # A blocked live trade is not a broker failure.
                pass
            else:
                consensus_status = "VETOED"
                rejection_reason = "MT5 broker execution failed to place order."

        # If rejected/vetoed, log rejection
        if consensus_status == "VETOED":
            explanation = payload.get("explanation", {})
            agreed = explanation.get("agreed_modules", [])
            disagreed = explanation.get("disagreed_modules", [])
            
            rejection_dict = {
                "symbol": symbol,
                "direction": direction,
                "confidence_score": score,
                "failed_conditions": disagreed + [rejection_reason],
                "reason_for_rejection": rejection_reason,
                "regime": payload.get("regime", "ranging"),
                "structure_pass": int("structure" in agreed),
                "liquidity_pass": int("smc" in agreed),
                "momentum_pass": int("momentum" in agreed),
                "volume_pass": int("volume" in agreed),
            }
            self.memory_agent.log_rejection(rejection_dict)

        # 4. Log the full decision details in agent_decisions table
        decision_log = {
            "proposal_id": proposal_msg.message_id,
            "symbol": symbol,
            "direction": direction,
            "market_analysis_score": score,
            "news_agent_vote": news_vote,
            "news_agent_reason": news_reason,
            "risk_agent_vote": risk_vote,
            "risk_agent_lots": risk_lots,
            "risk_agent_reason": risk_reason,
            "consensus_status": consensus_status,
            "execution_ticket": execution_ticket
        }
        self.memory_agent.log_decision(decision_log)
        
        return {
            "consensus_status": consensus_status,
            "ticket": execution_ticket,
            "trade_id": trade_id,
            "reason": rejection_reason if consensus_status == "VETOED" else "Executed successfully",
            "permission": permission.to_dict() if permission else None,
        }
