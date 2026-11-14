"""
╔══════════════════════════════════════════════════════════════════════╗
║       ZOHRA — Risk Guardian & Metals Trading Fix Tests             ║
║   Verifies position stacking fix and metals trading enablement     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import unittest
from unittest.mock import patch, MagicMock
from zohra.config.settings import (
    MAX_OPEN_POSITIONS, MAX_SCALE_UP_TICKETS_PER_SYMBOL,
    MAX_SECTOR_POSITIONS, METAL_SYMBOLS, METAL_LOT_MULTIPLIER
)


class TestSettingsConstants(unittest.TestCase):
    """Verify new constants are correctly defined."""

    def test_max_open_positions(self):
        self.assertEqual(MAX_OPEN_POSITIONS, 5)

    def test_max_scale_up_tickets_per_symbol(self):
        self.assertEqual(MAX_SCALE_UP_TICKETS_PER_SYMBOL, 3)

    def test_metal_symbols_defined(self):
        self.assertIn("XAUUSD", METAL_SYMBOLS)
        self.assertIn("XAGUSD", METAL_SYMBOLS)
        self.assertEqual(len(METAL_SYMBOLS), 2)

    def test_metal_lot_multiplier(self):
        self.assertEqual(METAL_LOT_MULTIPLIER, 0.5)

    def test_sector_positions_include_metals(self):
        self.assertIn("Metals", MAX_SECTOR_POSITIONS)
        self.assertEqual(MAX_SECTOR_POSITIONS["Metals"], 2)
        self.assertEqual(MAX_SECTOR_POSITIONS["Forex"], 3)


class TestRiskGuardianPositionLimits(unittest.TestCase):
    """Verify the position stacking / scale-up bypass is fixed."""

    def _make_position(self, symbol, direction="LONG", lots=0.01):
        return {"symbol": symbol, "direction": direction, "lots": lots, "type": 0 if direction == "LONG" else 1}

    @patch("zohra.core.risk_guardian.mt5_broker")
    def test_global_limit_enforced_even_for_scale_ups(self, mock_broker):
        """Even if a symbol qualifies for scale-up, it must not exceed MAX_OPEN_POSITIONS."""
        from zohra.core.risk_guardian import RiskGuardian
        guardian = RiskGuardian()

        mock_broker.is_connected.return_value = True
        mock_broker.get_equity.return_value = 200.0
        mock_broker.get_symbol_info.return_value = {"spread": 10, "point": 0.00001}

        # Create 5 open positions (= MAX_OPEN_POSITIONS)
        open_positions = [
            self._make_position("EURUSD"),
            self._make_position("GBPUSD"),
            self._make_position("USDJPY"),
            self._make_position("NZDUSD"),
            self._make_position("USDCHF"),
        ]

        # Try to add a 6th position — should be rejected even if it's a "scale-up" of existing symbol
        is_safe, reason = guardian.evaluate_execution_safety(
            "EURUSD", "LONG", 0.01, open_positions=open_positions
        )
        self.assertFalse(is_safe)
        self.assertIn("Maximum open position limit", reason)

    @patch("zohra.core.risk_guardian.mt5_broker")
    def test_per_symbol_limit_enforced(self, mock_broker):
        """No single symbol should exceed MAX_SCALE_UP_TICKETS_PER_SYMBOL tickets."""
        from zohra.core.risk_guardian import RiskGuardian
        guardian = RiskGuardian()

        mock_broker.is_connected.return_value = True
        mock_broker.get_equity.return_value = 200.0
        mock_broker.get_symbol_info.return_value = {"spread": 10, "point": 0.00001}

        # Create 3 open positions all on EURUSD (= MAX_SCALE_UP_TICKETS_PER_SYMBOL)
        open_positions = [
            self._make_position("EURUSD"),
            self._make_position("EURUSD"),
            self._make_position("EURUSD"),
        ]

        is_safe, reason = guardian.evaluate_execution_safety(
            "EURUSD", "LONG", 0.01, open_positions=open_positions
        )
        self.assertFalse(is_safe)
        self.assertIn("Scale-up limit reached", reason)

    @patch("zohra.core.risk_guardian.mt5_broker")
    def test_scale_up_allowed_within_limits(self, mock_broker):
        """A scale-up should be allowed if both per-symbol and global limits have room."""
        from zohra.core.risk_guardian import RiskGuardian
        guardian = RiskGuardian()

        mock_broker.is_connected.return_value = True
        mock_broker.get_equity.return_value = 200.0
        mock_broker.get_symbol_info.return_value = {"spread": 10, "point": 0.00001}

        # 2 positions on EURUSD (within per-symbol limit of 3), 3 total (within global limit of 5)
        open_positions = [
            self._make_position("EURUSD"),
            self._make_position("EURUSD"),
            self._make_position("GBPUSD"),
        ]

        is_safe, reason = guardian.evaluate_execution_safety(
            "EURUSD", "LONG", 0.01, open_positions=open_positions
        )
        # Should pass position limits (may still be blocked by correlation/spread, but not by position count)
        # We check that it's NOT blocked by scale-up/position limits specifically
        if not is_safe:
            self.assertNotIn("Scale-up limit", reason)
            self.assertNotIn("Maximum open position limit", reason)


class TestMetalsCorrelationExemption(unittest.TestCase):
    """Verify metals are exempt from correlation veto against each other."""

    @patch("zohra.core.risk_guardian.mt5_broker")
    def test_metal_to_metal_not_blocked_by_correlation(self, mock_broker):
        """XAUUSD and XAGUSD should not block each other via correlation filter."""
        from zohra.core.risk_guardian import RiskGuardian
        guardian = RiskGuardian()

        mock_broker.is_connected.return_value = True
        mock_broker.get_equity.return_value = 200.0
        mock_broker.get_symbol_info.return_value = {"spread": 10, "point": 0.01}

        open_positions = [
            {"symbol": "XAUUSD", "direction": "LONG", "lots": 0.01, "type": 0}
        ]

        is_safe, reason = guardian.evaluate_execution_safety(
            "XAGUSD", "LONG", 0.01, open_positions=open_positions
        )
        # Should NOT be blocked by correlation veto
        if not is_safe:
            self.assertNotIn("Correlation Veto", reason)
            self.assertNotIn("correlation", reason.lower())

    def test_metal_symbols_set(self):
        """METAL_SYMBOLS should contain exactly XAUUSD and XAGUSD."""
        self.assertEqual(METAL_SYMBOLS, {"XAUUSD", "XAGUSD"})


class TestMetalsSectorExposure(unittest.TestCase):
    """Verify metals sector is independent from forex sector limits."""

    @patch("zohra.core.risk_guardian.mt5_broker")
    def test_metals_have_separate_sector_limit(self, mock_broker):
        """3 forex positions should NOT block a metals trade."""
        from zohra.core.risk_guardian import RiskGuardian
        guardian = RiskGuardian()

        mock_broker.is_connected.return_value = True
        mock_broker.get_equity.return_value = 200.0
        mock_broker.get_symbol_info.return_value = {"spread": 10, "point": 0.01}

        # 3 forex positions (at sector limit)
        open_positions = [
            {"symbol": "EURUSD", "direction": "LONG", "lots": 0.01, "type": 0},
            {"symbol": "GBPUSD", "direction": "LONG", "lots": 0.01, "type": 0},
            {"symbol": "USDJPY", "direction": "LONG", "lots": 0.01, "type": 0},
        ]

        is_safe, reason = guardian.evaluate_execution_safety(
            "XAUUSD", "LONG", 0.01, open_positions=open_positions
        )
        # Should NOT be blocked by forex sector limit
        if not is_safe:
            self.assertNotIn("Sector exposure limit for Forex", reason)

    @patch("zohra.core.risk_guardian.mt5_broker")
    def test_metals_sector_limit_is_2(self, mock_broker):
        """Max 2 metal positions. A 3rd metal trade should be rejected."""
        from zohra.core.risk_guardian import RiskGuardian
        guardian = RiskGuardian()

        mock_broker.is_connected.return_value = True
        mock_broker.get_equity.return_value = 200.0
        mock_broker.get_symbol_info.return_value = {"spread": 10, "point": 0.01}

        # 2 metal positions (at sector limit)
        open_positions = [
            {"symbol": "XAUUSD", "direction": "LONG", "lots": 0.01, "type": 0},
            {"symbol": "XAGUSD", "direction": "LONG", "lots": 0.01, "type": 0},
        ]

        is_safe, reason = guardian.evaluate_execution_safety(
            "XAUUSD", "LONG", 0.01, open_positions=open_positions
        )
        self.assertFalse(is_safe)
        self.assertIn("Sector exposure limit for Metals", reason)


class TestRiskAgentMetalsExemption(unittest.TestCase):
    """Verify risk_agent also exempts metals from correlation veto."""

    def test_metal_correlation_exemption(self):
        """risk_agent.evaluate_portfolio_risk should not veto XAGUSD when XAUUSD is open."""
        from zohra.agents.risk_agent import RiskAgent
        agent = RiskAgent(starting_equity=200.0)

        open_positions = [
            {"symbol": "XAUUSD", "direction": "LONG", "lots": 0.01}
        ]

        approved, reason = agent.evaluate_portfolio_risk("XAGUSD", 0.01, open_positions, "LONG")
        if not approved:
            self.assertNotIn("Correlation", reason)


class TestCorrelationEngineMetalsExemption(unittest.TestCase):
    """Verify correlation engine exempts metal-to-metal in portfolio evaluation."""

    def test_portfolio_exposure_no_veto_for_metals(self):
        from zohra.core.correlation_engine import correlation_engine

        open_positions = [{"symbol": "XAUUSD", "direction": "LONG"}]
        max_corr, exp_score, reason = correlation_engine.evaluate_portfolio_exposure("XAGUSD", open_positions)

        # Metal-to-metal should be skipped, so no VETO Warning
        self.assertNotIn("VETO Warning", reason)


class TestScoutEngineLotSizing(unittest.TestCase):
    """Verify scout engine uses safe lot sizes for metals."""

    def test_metal_probe_lot_reduced(self):
        from zohra.core.scout_engine import ScoutEngine
        engine = ScoutEngine()
        # Metal probe lot should be at probe_lot_metal (0.01), not the old 0.10
        self.assertEqual(engine.probe_lot_metal, 0.01)
        self.assertFalse(hasattr(engine, 'probe_lot_gold'), "Old probe_lot_gold attribute should be removed")


if __name__ == "__main__":
    unittest.main()
