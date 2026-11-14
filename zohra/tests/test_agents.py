import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from zohra.core.agent_message import AgentMessage
from zohra.core.enums import MarketRegime, StrategyName, TradeQuality
from zohra.agents.memory_agent import MemoryAgent
from zohra.agents.news_agent import NewsAgent
from zohra.agents.risk_agent import RiskAgent
from zohra.agents.execution_agent import ExecutionAgent
from zohra.agents.performance_agent import PerformanceAgent
from zohra.security.permissions import TradingPermissionGateway

class TestMultiAgentTradingDesk(unittest.TestCase):

    def setUp(self):
        # Base trade proposal
        self.proposal_msg = AgentMessage(
            sender="MarketAnalysisAgent",
            message_type="PROPOSAL",
            payload={
                "symbol": "EURUSD",
                "direction": "LONG",
                "entry_price": 1.1000,
                "stop_loss": 1.0950,
                "take_profit": 1.1100,
                "regime": MarketRegime.TRENDING.value,
                "strategy": StrategyName.TREND_FOLLOWING.value,
                "confidence_score": 85,
                "explanation": {
                    "session": "overlap",
                    "summary_reason": "Bullish trend confirmed",
                    "scores_breakdown": {"structure": 90, "smc": 80, "momentum": 85}
                }
            }
        )

    def test_agent_message_serialization(self):
        """Verify AgentMessage formats to dictionary and reconstructs correctly."""
        msg_dict = self.proposal_msg.to_dict()
        self.assertEqual(msg_dict["sender"], "MarketAnalysisAgent")
        self.assertEqual(msg_dict["message_type"], "PROPOSAL")
        self.assertEqual(msg_dict["payload"]["symbol"], "EURUSD")

        reconstructed = AgentMessage.from_dict(msg_dict)
        self.assertEqual(reconstructed.message_id, self.proposal_msg.message_id)
        self.assertEqual(reconstructed.payload["confidence_score"], 85)

    def test_news_agent_verdicts(self):
        """Verify NewsAgent votes CLEAR/APPROVE or BLACKOUT/VETO correctly."""
        news_agent = NewsAgent()
        
        # 1. Clear state
        vote_msg = news_agent.evaluate_proposal(self.proposal_msg)
        self.assertEqual(vote_msg.payload["vote"], "APPROVE")
        self.assertIn("clear", vote_msg.payload["reason"].lower())

        # 2. Blackout state (CPI release time overlap)
        news_agent.add_event(
            event_name="CPI Release",
            currency="USD",
            event_time=datetime.utcnow().isoformat(),
            before=30,
            after=30
        )
        veto_msg = news_agent.evaluate_proposal(self.proposal_msg)
        self.assertEqual(veto_msg.payload["vote"], "VETO")
        self.assertIn("blackout", veto_msg.payload["reason"].lower())

    @patch("zohra.agents.risk_agent.mt5_broker")
    @patch("zohra.agents.risk_agent.scorer")
    def test_risk_agent_sizing_and_limits(self, mock_scorer, mock_mt5):
        """Verify RiskAgent calculates dynamic position sizing and handles risk boundaries."""
        risk_agent = RiskAgent(starting_equity=10000.0)
        
        # Mock MT5 broker
        mock_mt5.get_equity.return_value = 10000.0
        mock_mt5.get_open_positions.return_value = []
        
        # Mock Scorer kill switch (not blocked)
        mock_scorer.check_kill_switch.return_value = (False, "")
        # Mock position sizing (Lots = 0.15 for grade A)
        mock_scorer.get_position_size.return_value = 0.15

        # 1. Successful Approval
        vote_msg = risk_agent.evaluate_proposal(self.proposal_msg)
        self.assertEqual(vote_msg.payload["vote"], "APPROVE")
        self.assertEqual(vote_msg.payload["lots"], 0.15)
        self.assertIn("passed", vote_msg.payload["reason"].lower())

        # 2. Daily Loss Kill Switch Veto
        mock_scorer.check_kill_switch.return_value = (True, "Daily loss limit hit")
        veto_msg = risk_agent.evaluate_proposal(self.proposal_msg)
        self.assertEqual(veto_msg.payload["vote"], "VETO")
        self.assertEqual(veto_msg.payload["lots"], 0.0)
        self.assertIn("exceeded", veto_msg.payload["reason"].lower())

        # 3. Max open positions reached veto
        mock_scorer.check_kill_switch.return_value = (False, "")
        mock_mt5.get_open_positions.return_value = [1, 2, 3, 4, 5]  # MAX_OPEN_POSITIONS = 5
        veto_positions_msg = risk_agent.evaluate_proposal(self.proposal_msg)
        self.assertEqual(veto_positions_msg.payload["vote"], "VETO")
        self.assertIn("limit", veto_positions_msg.payload["reason"].lower())

    @patch("zohra.agents.execution_agent.mt5_broker")
    def test_execution_agent_consensus(self, mock_mt5):
        """Verify ExecutionAgent validates votes, halts on vetoes, and routes orders on consensus."""
        # Mock news and risk agents
        mock_news = MagicMock()
        mock_risk = MagicMock()
        mock_memory = MagicMock()
        
        # Create execution agent
        exec_agent = ExecutionAgent(
            news_agent=mock_news,
            risk_agent=mock_risk,
            memory_agent=mock_memory,
            min_score_threshold=70,
            # Exercise the order path with an explicit test-only simulated
            # broker. Paper mode must never authorize the mocked MT5 broker.
            permission_gateway=TradingPermissionGateway(execution_mode="simulated"),
            broker=mock_mt5,
        )
        self.proposal_msg.payload["broker"] = "simulated"

        # Mock MT5 execution
        mock_mt5.open_trade.return_value = {"ticket": 88888, "symbol": "EURUSD"}

        # Case 1: Full consensus (All APPROVE)
        mock_news.evaluate_proposal.return_value = AgentMessage(
            sender="NewsAgent",
            message_type="VOTE",
            payload={"vote": "APPROVE", "reason": "Clear"}
        )
        mock_risk.evaluate_proposal.return_value = AgentMessage(
            sender="RiskAgent",
            message_type="VOTE",
            payload={"vote": "APPROVE", "lots": 0.2, "reason": "Passed"}
        )

        res = exec_agent.process_consensus_voting(self.proposal_msg)
        self.assertEqual(res["consensus_status"], "APPROVED")
        self.assertEqual(res["ticket"], 88888)
        mock_mt5.open_trade.assert_called_once()
        mock_memory.log_trade.assert_called_once()
        mock_memory.log_decision.assert_called_once()

        # Reset mocks
        mock_mt5.open_trade.reset_mock()
        mock_memory.log_trade.reset_mock()
        mock_memory.log_decision.reset_mock()

        # Case 2: Risk Agent issues VETO
        mock_risk.evaluate_proposal.return_value = AgentMessage(
            sender="RiskAgent",
            message_type="VOTE",
            payload={"vote": "VETO", "lots": 0.0, "reason": "Max positions"}
        )

        res_veto = exec_agent.process_consensus_voting(self.proposal_msg)
        self.assertEqual(res_veto["consensus_status"], "VETOED")
        self.assertIsNone(res_veto["ticket"])
        mock_mt5.open_trade.assert_not_called()
        mock_memory.log_trade.assert_not_called()
        mock_memory.log_rejection.assert_called_once()
        mock_memory.log_decision.assert_called_once()

    def test_performance_agent_reviews(self):
        """Verify PerformanceAgent parses trading history and issues optimizations advice."""
        perf_agent = PerformanceAgent()
        
        # Synthesize closed trade lists
        closed_trades = [
            {"pnl_usd": 150.0, "strategy_used": "trend_following", "symbol": "EURUSD", "timestamp_close": "2026-06-05T12:00:00"},
            {"pnl_usd": 200.0, "strategy_used": "trend_following", "symbol": "EURUSD", "timestamp_close": "2026-06-05T12:00:00"},
            {"pnl_usd": -50.0, "strategy_used": "trend_following", "symbol": "EURUSD", "timestamp_close": "2026-06-05T12:00:00"},
            {"pnl_usd": 100.0, "strategy_used": "trend_following", "symbol": "EURUSD", "timestamp_close": "2026-06-05T12:00:00"},
            {"pnl_usd": 300.0, "strategy_used": "trend_following", "symbol": "EURUSD", "timestamp_close": "2026-06-05T12:00:00"}
        ] # 4 wins, 1 loss = 80% Win Rate, PF = 750/50 = 15.0 (excellent)

        rejections = [{"reason_for_rejection": "Spread high", "structure_pass": 1, "liquidity_pass": 1}]
        
        suggestions = perf_agent.generate_optimization_suggestions(closed_trades, rejections)
        self.assertTrue(any("exceptionally well" in s for s in suggestions))

if __name__ == "__main__":
    unittest.main()
