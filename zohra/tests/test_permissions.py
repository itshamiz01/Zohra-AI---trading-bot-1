import unittest

from zohra.brokers.pipeline import PipelineContext, create_default_pipeline
from zohra.security.permissions import TradingPermissionGateway


class TestTradingPermissions(unittest.TestCase):
    def test_live_execution_requires_preauthorization(self):
        gateway = TradingPermissionGateway(
            execution_mode="live",
            live_trading_preauthorized=False,
        )

        decision = gateway.authorize_trade_execution({
            "symbol": "EURUSD",
            "direction": "LONG",
            "lots": 0.1,
            "broker": "mt5",
            "risk_approved": True,
            "consensus_status": "APPROVED",
        })

        self.assertFalse(decision.approved)
        self.assertIn("pre-authorization", decision.reason)

    def test_pipeline_rejects_without_risk_evaluator(self):
        pipeline = create_default_pipeline(
            permission_gateway=TradingPermissionGateway(
                execution_mode="live",
                live_trading_preauthorized=True,
            ),
            executor=lambda context: {"ticket": 12345},
        )
        context = PipelineContext(
            symbol="EURUSD",
            direction="LONG",
            stop_loss=1.0950,
            take_profit=1.1100,
            position_size_lots=0.1,
        )

        result = pipeline.run(context)

        self.assertEqual(result.status.value, "FAILED")
        self.assertIn("No risk evaluator configured", result.execution_error)
        self.assertEqual(result.ticket, 0)

    def test_pipeline_allows_preauthorized_live_trade(self):
        pipeline = create_default_pipeline(
            risk_evaluator=lambda context: {
                "approved": True,
                "reason": "Risk Chairman approved",
                "lots": 0.1,
            },
            permission_gateway=TradingPermissionGateway(
                execution_mode="live",
                live_trading_preauthorized=True,
            ),
            executor=lambda context: {"ticket": 12345, "price": 1.1001, "lots": 0.1},
        )
        context = PipelineContext(
            symbol="EURUSD",
            direction="LONG",
            stop_loss=1.0950,
            take_profit=1.1100,
        )

        result = pipeline.run(context)

        self.assertEqual(result.status.value, "COMPLETED")
        self.assertTrue(result.permission_approved)
        self.assertEqual(result.ticket, 12345)


if __name__ == "__main__":
    unittest.main()
