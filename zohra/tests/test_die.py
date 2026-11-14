"""
Unit tests for the Decision Intelligence Engine (DIE)
Run via: python -m unittest zohra/tests/test_die.py
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock, patch

from zohra.core.enums import MarketRegime, Direction, StrategyName
from zohra.core.market_regime import MarketRegimeDetector
from zohra.core.adaptive_scorer import AdaptiveScorer
from zohra.core.decision_engine import DecisionEngine, DecisionExplanation


class TestDecisionIntelligenceEngine(unittest.TestCase):

    def setUp(self):
        # Create a synthetic dataset of 60 bars
        dates = pd.date_range(end=datetime.utcnow(), periods=60, freq='h')
        self.df_base = pd.DataFrame(index=dates)
        self.df_base['open'] = 1.1000
        self.df_base['high'] = 1.1020
        self.df_base['low'] = 1.0980
        self.df_base['close'] = 1.1010
        self.df_base['tick_volume'] = 1000

    def test_regime_detector_trending(self):
        """Verify that aligned rising EMAs and high ADX classify as TRENDING."""
        df = self.df_base.copy()
        # Create a strong upward trend
        close_vals = [1.1000 + i * 0.0010 for i in range(60)]
        df['close'] = close_vals
        df['high'] = [c + 0.0005 for c in close_vals]
        df['low'] = [c - 0.0005 for c in close_vals]
        df['open'] = [c - 0.0002 for c in close_vals]
        df['tick_volume'] = 1000

        detector = MarketRegimeDetector(adx_period=5, bb_period=10, atr_period=5)
        regime = detector.detect(df)
        
        # Should be classified as TRENDING due to clear upward trend and EMA alignment
        self.assertEqual(regime, MarketRegime.TRENDING)

    def test_regime_detector_news_driven(self):
        """Verify that an extremely large candle classifies as NEWS_DRIVEN."""
        df = self.df_base.copy()
        
        # Last candle is massive
        df.loc[df.index[-1], 'open'] = 1.1000
        df.loc[df.index[-1], 'close'] = 1.1500  # +500 pips
        df.loc[df.index[-1], 'high'] = 1.1510
        df.loc[df.index[-1], 'low'] = 1.0990

        detector = MarketRegimeDetector(adx_period=5, bb_period=10, atr_period=5)
        regime = detector.detect(df)
        self.assertEqual(regime, MarketRegime.NEWS_DRIVEN)

    @patch('zohra.core.adaptive_scorer.db')
    def test_adaptive_scorer_performance_weights(self, mock_db):
        """Verify that adaptive weight weights adapt dynamically based on DB trade logs."""
        scorer = AdaptiveScorer(min_history_count=3)

        # 1. Test case: perfect history (100% Win Rate, PF = 2.0)
        # Structure module has agreed (score_structure = 100) and won (pnl_usd > 0)
        mock_db._execute.return_value = [
            {"pnl_usd": 150.0, "score_structure": 100, "score_liquidity": 10, "score_smc": 10},
            {"pnl_usd": 100.0, "score_structure": 100, "score_liquidity": 10, "score_smc": 10},
            {"pnl_usd": 200.0, "score_structure": 100, "score_liquidity": 10, "score_smc": 10},
        ]

        weights = scorer.get_adaptive_weights(MarketRegime.TRENDING, StrategyName.TREND_FOLLOWING.value)
        
        # Base weight for structure in trending is 25.0
        # Win rate = 100% (1.0), Profit Factor = 2.0
        # eta = 0.6 * 1.0 + 0.4 * min(2.0, 2.0 / 1.5) = 0.6 + 0.4 * 1.33 = 1.13
        # Weight should be higher than base (25.0 * 1.13 = ~28.3)
        self.assertGreater(weights['structure'], 25.0)

        # 2. Test case: losing history (0% Win Rate)
        mock_db._execute.return_value = [
            {"pnl_usd": -100.0, "score_structure": 100, "score_liquidity": 10, "score_smc": 10},
            {"pnl_usd": -50.0, "score_structure": 100, "score_liquidity": 10, "score_smc": 10},
            {"pnl_usd": -200.0, "score_structure": 100, "score_liquidity": 10, "score_smc": 10},
        ]

        weights = scorer.get_adaptive_weights(MarketRegime.TRENDING, StrategyName.TREND_FOLLOWING.value)
        
        # Weight should be severely discounted to minimum clamp boundary (25.0 * 0.2 = 5.0)
        self.assertEqual(weights['structure'], 5.0)

    @patch('zohra.core.decision_engine.regime_detector')
    @patch('zohra.strategies.trend_following.trend_following_strategy.generate_signal')
    @patch('zohra.core.adaptive_scorer.adaptive_scorer.evaluate_confluence')
    def test_decision_engine_pipeline(self, mock_confl, mock_signal, mock_detector):
        """Verify that DecisionEngine processes inputs and creates a BUY execution decision."""
        engine = DecisionEngine(min_score_threshold=70)

        # Mock regime as TRENDING
        mock_detector.detect_with_details.return_value = {"regime": MarketRegime.TRENDING}
        mock_detector.detect.return_value = MarketRegime.TRENDING

        # Mock strategy generates a BUY signal
        mock_signal.return_value = {
            "strategy": StrategyName.TREND_FOLLOWING.value,
            "symbol": "EURUSD",
            "direction": Direction.LONG.value,
            "entry_price": 1.1000,
            "stop_loss": 1.0950,
            "take_profit": 1.1100,
            "reason": "Test setup"
        }

        # Mock confluence yields score of 85 (high confluence)
        mock_confl.return_value = {
            "final_score": 85,
            "scores": {"structure": 90, "momentum": 80, "session": 80},
            "weights": {"structure": 25.0, "momentum": 15.0, "session": 10.0},
            "reasons": {"structure": "HH HL", "momentum": "MACD cross", "session": "overlap"}
        }

        df = self.df_base.copy()
        explanation = engine.process_data(df, df, df, "EURUSD")

        self.assertEqual(explanation.decision, "BUY")
        self.assertEqual(explanation.confidence_score, 85)
        self.assertEqual(explanation.strategy_used, StrategyName.TREND_FOLLOWING.value)
        self.assertIn("structure", explanation.agreed_modules)


if __name__ == '__main__':
    unittest.main()
