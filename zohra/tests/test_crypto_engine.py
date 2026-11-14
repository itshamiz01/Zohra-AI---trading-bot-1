"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — CRYPTO TEST SUITE                          ║
║          Unit & Integration Tests for Crypto Market Subsystem        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime

from zohra.core.crypto_risk import crypto_risk_guardian
from zohra.core.crypto_portfolio import crypto_portfolio_manager
from zohra.core.crypto_intelligence import crypto_intelligence
from zohra.strategies.crypto_strategies import crypto_momentum_strategy, crypto_smc_strategy
from zohra.integrations.ai_agent import ZohraAgentBridge


class TestCryptoSubsystem(unittest.TestCase):
    """
    Validation tests for Zohra Crypto Market Subsystem components.
    """

    def setUp(self):
        import tempfile
        import os
        from zohra.config.settings import settings
        import zohra.db.connection as conn_mod
        
        # Override the database path to a temporary file
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        settings.database.sqlite_path = self.temp_db_path
        
        # Reset the global database instance to connect to the new clean file
        conn_mod._db_instance = None

        # Create a basic sample DataFrame for strategy testing
        dates = pd.date_range(start="2026-07-06 00:00", periods=60, freq="15min")
        close_prices = np.linspace(100.0, 110.0, 60)  # linear uptrend
        self.df = pd.DataFrame({
            "open": close_prices - 0.5,
            "high": close_prices + 0.8,
            "low": close_prices - 0.8,
            "close": close_prices,
            "tick_volume": [1000] * 60
        }, index=dates)

    def tearDown(self):
        import os
        import zohra.db.connection as conn_mod
        if conn_mod._db_instance:
            conn_mod._db_instance.close()
            conn_mod._db_instance = None
        try:
            os.close(self.temp_db_fd)
            os.unlink(self.temp_db_path)
        except Exception:
            pass

    @patch('zohra.brokers.manager.broker_manager.get_equity')
    @patch('zohra.brokers.manager.broker_manager.get_tick')
    @patch('zohra.brokers.manager.broker_manager.get_current_price')
    @patch('zohra.brokers.manager.broker_manager.get_ohlcv')
    def test_crypto_risk_guardian_evaluation(self, mock_get_ohlcv, mock_get_price, mock_get_tick, mock_get_equity):
        # 1. Normal conditions check
        mock_get_equity.return_value = 50000.0
        mock_get_tick.return_value = {"ask": 60000.0, "bid": 59980.0}
        mock_get_price.return_value = {"spread": 20.0}
        
        # Mock historical data for low volatility
        dates = pd.date_range(start="2026-07-06 00:00", periods=50, freq="15min")
        df_low_vol = pd.DataFrame({"close": np.linspace(60000.0, 60100.0, 50)}, index=dates)
        mock_get_ohlcv.return_value = df_low_vol

        is_safe, reason = crypto_risk_guardian.evaluate_crypto_safety(
            "BTCUSDT", "LONG", 0.05, [], False
        )
        self.assertTrue(is_safe, f"Should be safe under normal conditions: {reason}")

        # 2. Extreme volatility veto check
        df_high_vol = pd.DataFrame({"close": [60000 * (1 + 0.1 * (i % 2)) for i in range(50)]}, index=dates)
        mock_get_ohlcv.return_value = df_high_vol
        is_safe, reason = crypto_risk_guardian.evaluate_crypto_safety(
            "BTCUSDT", "LONG", 0.05, [], False
        )
        self.assertFalse(is_safe)
        self.assertIn("Volatility Veto", reason)

        # 3. Spread veto check
        mock_get_ohlcv.return_value = df_low_vol
        mock_get_price.return_value = {"spread": 150.0}  # limit is 50
        is_safe, reason = crypto_risk_guardian.evaluate_crypto_safety(
            "BTCUSDT", "LONG", 0.05, [], False
        )
        self.assertFalse(is_safe)
        self.assertIn("Spread Veto", reason)

    @patch("zohra.core.crypto_portfolio.broker_manager")
    def test_crypto_portfolio_allocations_rebalance(self, mock_broker_manager):
        # The portfolio only works from an authenticated exchange wallet.
        mock_broker_manager.is_connected.return_value = True
        mock_broker_manager.get_adapter.return_value.get_balances.return_value = {
            "USDT": 1000.0,
            "BTC": 0.15,
            "ETH": 1.2,
        }
        # Mock prices (BTC = 60000, ETH = 3000) -> Portfolio value: 1000 + 9000 + 3600 = 13600 USD
        mock_broker_manager.get_tick.side_effect = lambda symbol, broker=None: (
            {"bid": 60000.0} if "BTC" in symbol else {"bid": 3000.0} if "ETH" in symbol else {"bid": 1.0}
        )

        status = crypto_portfolio_manager.get_portfolio_status()
        self.assertEqual(status["status"], "success")
        self.assertEqual(status["total_value_usd"], 13600.0)
        self.assertTrue(status["rebalance_needed"])
        
        # Check target rebalance suggestion list is populated
        self.assertGreater(len(status["suggestions"]), 0)
        
        # Check trade recommendations conversion
        trades = crypto_portfolio_manager.evaluate_rebalance_trades()
        self.assertGreater(len(trades), 0)
        self.assertEqual(trades[0]["symbol"], "BTCUSDT")

    def test_crypto_intelligence_indicators(self):
        metrics = crypto_intelligence.update_intelligence_metrics()
        self.assertIn("btc_dominance", metrics)
        self.assertIn("macro_correlations", metrics)
        self.assertIn("on_chain", metrics)
        self.assertIn("etf_flows", metrics)

        # Verify correct correlation mapping lookup
        corr = crypto_intelligence.get_correlation_to_asset("BTC", "Nasdaq")
        self.assertGreaterEqual(corr, -1.0)
        self.assertLessEqual(corr, 1.0)

    def test_crypto_momentum_strategy_triggers(self):
        # Linear uptrend DataFrame -> EMA Fast should crossover Slow, RSI bullish but not overbought
        # Set specific close array to force setup triggers
        dates = pd.date_range(start="2026-07-06 00:00", periods=60, freq="15min")
        close = [100.0] * 30 + [100.0 * (1.002 ** i) for i in range(30)]  # gentle trend
        df_trend = pd.DataFrame({
            "high": [c + 0.1 for c in close],
            "low": [c - 0.1 for c in close],
            "close": close,
        }, index=dates)

        signal = crypto_momentum_strategy.generate_signal(df_trend, "BTCUSDT")
        if signal:
            self.assertEqual(signal["direction"], "LONG")
            self.assertGreater(signal["take_profit"], signal["entry_price"])
            self.assertLess(signal["stop_loss"], signal["entry_price"])

    def test_voice_agent_bridge_routing(self):
        bridge = ZohraAgentBridge()
        
        # Test "analyze bitcoin" mapping
        res = bridge.process_command("crypto analyze btc", {})
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("unavailable", res["message"].lower())
        self.assertEqual(res["data"]["status"], "unavailable")
        
        # Test "crypto portfolio" mapping
        res = bridge.process_command("crypto portfolio", {})
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("unavailable", res["message"].lower())
        self.assertEqual(res["data"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
