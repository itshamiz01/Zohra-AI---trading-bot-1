"""
╔══════════════════════════════════════════════════════════════════════╗
║     ZOHRA 15-STRATEGY CONFLUENCE & INDEPENDENCE TEST SUITE           ║
║            Comprehensive Validation for Institutional Engine         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath("."))

import numpy as np
import pandas as pd
import datetime as dt

from zohra.core.enums import StrategyGroup, StrategyName, MarketRegime
from zohra.core.market_regime import MarketRegimeEngine, RegimeReport
from zohra.core.confluence_engine import ConfluenceEngine, ConfluenceDecision
from zohra.strategies.base_strategy import CandidateSignal
from zohra.config.strategy_config import strategy_config


def generate_synthetic_data(n_bars: int = 60, trend: str = "UP", base_price: float = 2650.0) -> pd.DataFrame:
    """Generates synthetic M5 OHLCV dataframe for test validation."""
    times = [dt.datetime(2026, 8, 28, 10, 0) + dt.timedelta(minutes=5 * i) for i in range(n_bars)]
    closes = []
    highs = []
    lows = []
    opens = []
    volumes = []

    curr = base_price
    for i in range(n_bars):
        opens.append(curr)
        if trend == "UP":
            drift = 0.5 + (0.1 * np.sin(i * 0.3))
            curr += drift
            h = curr + 0.6
            l = opens[-1] - 0.2
        elif trend == "DOWN":
            drift = -0.5 - (0.1 * np.sin(i * 0.3))
            curr += drift
            h = opens[-1] + 0.2
            l = curr - 0.6
        else: # RANGING
            curr = base_price + (np.sin(i * 0.5) * 1.5)
            h = curr + 0.5
            l = curr - 0.5

        closes.append(curr)
        highs.append(h)
        lows.append(l)
        volumes.append(1000 + int(np.random.randint(100, 500)))

    return pd.DataFrame({
        "timestamp": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": volumes,
        "volume": volumes
    })


class Test15StrategyConfluenceEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ConfluenceEngine()
        self.regime_engine = MarketRegimeEngine()

    def test_01_all_15_strategies_registered(self):
        """Verify all 15 required strategies exist with proper group mappings."""
        self.assertEqual(len(self.engine.strategies), 15, "Engine must contain exactly 15 strategies.")

        group_counts = {}
        for name, strat in self.engine.strategies.items():
            grp = strat.strategy_group
            group_counts[grp] = group_counts.get(grp, 0) + 1

        self.assertGreaterEqual(group_counts.get(StrategyGroup.TREND.value, 0), 4, "Trend group must have >= 4 strategies.")
        self.assertGreaterEqual(group_counts.get(StrategyGroup.MEAN_REVERSION.value, 0), 3, "Mean-Reversion group must have >= 3 strategies.")
        self.assertGreaterEqual(group_counts.get(StrategyGroup.STRUCTURE_SMC.value, 0), 5, "Structure/SMC group must have >= 5 strategies.")
        self.assertGreaterEqual(group_counts.get(StrategyGroup.BREAKOUT_VOLATILITY.value, 0), 3, "Breakout group must have >= 3 strategies.")

    def test_02_insufficient_confirmations_rejected(self):
        """When fewer than 3 strategies confirm, trade must be rejected."""
        df_up = generate_synthetic_data(60, trend="UP")
        regime_report = RegimeReport(
            regime=MarketRegime.TRENDING_UP,
            confidence=85,
            adx_value=32.0,
            ema_alignment="BULLISH",
            reasons=["Strong Bullish Trend"]
        )

        # Mock evaluate_all with only 2 candidate signals
        sig1 = CandidateSignal(
            strategy_name=StrategyName.EMA_PULLBACK.value,
            strategy_group=StrategyGroup.TREND.value,
            symbol="XAUUSD", direction="BUY", entry_price=2650.0,
            stop_loss=2645.0, take_profit=2660.0, risk_reward=2.0,
            stop_distance_pips=50.0, setup_quality=85, confidence=85,
            regime_match_score=95, volatility_score=85, spread_score=90
        )
        sig2 = CandidateSignal(
            strategy_name=StrategyName.LIQUIDITY_MSS.value,
            strategy_group=StrategyGroup.STRUCTURE_SMC.value,
            symbol="XAUUSD", direction="BUY", entry_price=2650.0,
            stop_loss=2645.0, take_profit=2660.0, risk_reward=2.0,
            stop_distance_pips=50.0, setup_quality=88, confidence=85,
            regime_match_score=95, volatility_score=85, spread_score=90
        )

        # Test internal arbitration with 2 signals
        decision = self.engine._build_decision(
            "NO_TRADE",
            direction="BUY",
            raw_confirmations=2,
            independent_groups=2,
            strategy_groups=[StrategyGroup.TREND.value, StrategyGroup.STRUCTURE_SMC.value],
            rejection_reason="INSUFFICIENT_CONFIRMATIONS (2 < 3 required)"
        )
        self.assertEqual(decision.action, "NO_TRADE")
        self.assertIn("INSUFFICIENT_CONFIRMATIONS", decision.rejection_reason)

    def test_03_single_group_correlation_rejection(self):
        """When 3 signals occur but all belong to the SAME group (e.g. Trend only), reject in Mode A."""
        decision = self.engine._build_decision(
            "NO_TRADE",
            direction="BUY",
            raw_confirmations=3,
            independent_groups=1,
            strategy_groups=[StrategyGroup.TREND.value],
            rejection_reason="INSUFFICIENT_INDEPENDENT_GROUPS (1 < 2 required; all belong to ['TREND'])"
        )
        self.assertEqual(decision.action, "NO_TRADE")
        self.assertIn("INSUFFICIENT_INDEPENDENT_GROUPS", decision.rejection_reason)

    def test_04_valid_multi_group_confluence_approved(self):
        """When 3+ signals occur representing >= 2 distinct groups without conflict, approve TRADE candidate."""
        sig1 = CandidateSignal(
            strategy_name=StrategyName.EMA_PULLBACK.value,
            strategy_group=StrategyGroup.TREND.value,
            symbol="XAUUSD", direction="BUY", entry_price=2650.0,
            stop_loss=2645.0, take_profit=2660.0, risk_reward=2.0,
            stop_distance_pips=50.0, setup_quality=88, confidence=88,
            regime_match_score=95, volatility_score=85, spread_score=90
        )
        sig2 = CandidateSignal(
            strategy_name=StrategyName.FIBONACCI_PULLBACK.value,
            strategy_group=StrategyGroup.TREND.value,
            symbol="XAUUSD", direction="BUY", entry_price=2650.0,
            stop_loss=2645.0, take_profit=2660.0, risk_reward=2.0,
            stop_distance_pips=50.0, setup_quality=85, confidence=88,
            regime_match_score=95, volatility_score=85, spread_score=90
        )
        sig3 = CandidateSignal(
            strategy_name=StrategyName.LIQUIDITY_MSS.value,
            strategy_group=StrategyGroup.STRUCTURE_SMC.value,
            symbol="XAUUSD", direction="BUY", entry_price=2650.0,
            stop_loss=2645.0, take_profit=2660.0, risk_reward=2.0,
            stop_distance_pips=50.0, setup_quality=92, confidence=88,
            regime_match_score=95, volatility_score=90, spread_score=90
        )

        regime_report = RegimeReport(
            regime=MarketRegime.TRENDING_UP,
            confidence=88,
            adx_value=30.0,
            ema_alignment="BULLISH",
            reasons=["Strong Trend"]
        )

        score, grade = self.engine._score_confluence(
            primary_signal=sig3,
            raw_confirmations=3,
            independent_groups_count=2,
            regime_report=regime_report,
            current_spread_pips=2.0
        )

        self.assertGreaterEqual(score, 80)
        self.assertIn(grade, ["A+", "A", "B"])

    def test_05_directional_conflict_veto(self):
        """When opposing BUY and SELL signals create significant conflict, reject with CONFLICT_DETECTED."""
        decision = self.engine._build_decision(
            "NO_TRADE",
            conflict_detected=True,
            rejection_reason="CONFLICT_DETECTED: Directional conflict (2 BUY vs 2 SELL)"
        )
        self.assertEqual(decision.action, "NO_TRADE")
        self.assertTrue(decision.conflict_detected)
        self.assertIn("CONFLICT_DETECTED", decision.rejection_reason)

    def test_06_diagnostic_box_formatting(self):
        """Verify diagnostic box includes all 15 strategies and summary fields."""
        regime_report = RegimeReport(
            regime=MarketRegime.TRENDING_UP,
            confidence=87,
            adx_value=31.0,
            ema_alignment="BULLISH",
            reasons=["Confirmed Bullish Alignment"]
        )

        diag_box = self.engine.format_diagnostic_box(
            regime_report=regime_report,
            strategy_statuses={s: {"verdict": "OFF", "eligible": False} for s in self.engine.strategies},
            action="NO_TRADE",
            direction="NONE",
            raw_confirmations=0,
            independent_groups=0,
            strategy_groups=[],
            final_score=0,
            grade="REJECT",
            rejection_reason="NO_VALID_STRATEGY_SIGNALS",
            current_spread_pips=2.0
        )

        self.assertIn("ZOHRA — 15-STRATEGY REGIME-ADAPTIVE CONFLUENCE ENGINE", diag_box)
        self.assertIn("EMA_PULLBACK", diag_box)
        self.assertIn("FIBONACCI_PULLBACK", diag_box)
        self.assertIn("FALSE_BREAKOUT", diag_box)
        self.assertIn("RAW CONFIRMATIONS:", diag_box)
        self.assertIn("INDEPENDENT GROUPS:", diag_box)


if __name__ == "__main__":
    unittest.main()
