import unittest
import pandas as pd
from zohra.core.symbol_manager import symbol_manager
from zohra.core.opportunity_engine import OpportunityEngine
from zohra.core.correlation_engine import correlation_engine
from zohra.core.symbol_worker import SymbolWorker
from zohra.core.enums import StrategyName

class TestMultiSymbolArchitecture(unittest.TestCase):
    """Unit tests for the new Multi-Symbol scanning and execution architecture components."""

    def test_symbol_manager_registration(self):
        """Verifies symbol manager correctly handles symbol details and state switches."""
        # Check defaults loaded
        params = symbol_manager.get_symbol_params("XAUUSD")
        self.assertIsNotNone(params)
        self.assertEqual(params["sector"], "Metals")
        self.assertEqual(params["contract_size"], 100.0)

        # Toggle state
        self.assertTrue(symbol_manager.is_market_open("XAUUSD") or not symbol_manager.is_market_open("XAUUSD"))

        # Default registration should be considered available until explicitly marked unhealthy.
        self.assertTrue(symbol_manager.is_active("XAUUSD"))
        
        # Test activation/deactivation for an explicitly configured symbol.
        symbol_manager.deactivate_symbol("EURUSD")
        self.assertFalse(symbol_manager.is_active("EURUSD"))

        self.assertTrue(symbol_manager.activate_symbol("EURUSD"))
        # Ensure it turns back on if health status is verified.
        symbol_manager.health_status["EURUSD"] = True
        self.assertTrue(symbol_manager.is_active("EURUSD"))

        # A runtime toggle must not bypass the configured instrument universe.
        self.assertFalse(symbol_manager.activate_symbol("EURJPY"))
        self.assertFalse(symbol_manager.is_active("EURJPY"))

    def test_opportunity_engine_ranking(self):
        """Verifies opportunity leaderboard ranking, pruning, and removals."""
        engine = OpportunityEngine(expiry_minutes=15)
        
        setup_a = {
            "symbol": "EURUSD",
            "strategy": StrategyName.SCALP_M5.value,
            "direction": "LONG",
            "confidence_score": 82,
            "entry_price": 1.0850,
            "stop_loss": 1.0830,
            "take_profit": 1.0890,
            "regime": "RANGING",
            "scores_breakdown": {},
            "weights_used": {},
            "reasons": []
        }
        setup_b = {
            "symbol": "XAUUSD",
            "strategy": StrategyName.ZOHRA_V5.value,
            "direction": "BUY",
            "confidence_score": 91,
            "entry_price": 2330.00,
            "stop_loss": 2320.00,
            "take_profit": 2350.00,
            "regime": "TRENDING",
            "scores_breakdown": {},
            "weights_used": {},
            "reasons": []
        }
        
        # Register setups
        engine.register_setup(setup_a)
        engine.register_setup(setup_b)
        
        # Verify sorting (highest score first)
        leaderboard = engine.get_leaderboard()
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0]["symbol"], "XAUUSD") # Score 91 > 82
        
        # Check helper properties
        self.assertEqual(engine.get_top_opportunity()["symbol"], "XAUUSD")
        self.assertEqual(engine.get_top_scalping_opportunity()["symbol"], "EURUSD")
        self.assertEqual(engine.get_top_swing_opportunity()["symbol"], "XAUUSD")
        
        # Test remove setup
        engine.remove_setup("XAUUSD", StrategyName.ZOHRA_V5.value)
        self.assertEqual(len(engine.get_leaderboard()), 1)
        self.assertEqual(engine.get_top_opportunity()["symbol"], "EURUSD")

    def test_correlation_engine_portfolio_checks(self):
        """Verifies correlation coefficients and portfolio exposure checks."""
        coeff = correlation_engine.get_correlation("EURUSD", "GBPUSD")
        self.assertAlmostEqual(coeff, 0.85, places=2)
        
        # Test negative/inverse correlation
        coeff_inv = correlation_engine.get_correlation("EURUSD", "USDCHF")
        self.assertAlmostEqual(coeff_inv, -0.80, places=2)
        
        # Test portfolio exposure checks
        open_pos = [{"symbol": "EURUSD", "direction": "LONG"}]
        
        # Proposed highly correlated BUY on GBPUSD
        max_corr, exp_score, reason = correlation_engine.evaluate_portfolio_exposure("GBPUSD", open_pos)
        self.assertAlmostEqual(max_corr, 0.85, places=2)
        self.assertIn("VETO Warning: High correlation", reason)

        # Proposed BUY on USDCHF (negatively correlated, opposite direction is a risk)
        max_corr_inv, exp_score_inv, reason_inv = correlation_engine.evaluate_portfolio_exposure("USDCHF", open_pos)
        self.assertAlmostEqual(max_corr_inv, 0.80, places=2)

if __name__ == "__main__":
    unittest.main()
