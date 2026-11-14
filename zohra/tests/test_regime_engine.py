import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import unittest
import pandas as pd
import numpy as np

from zohra.core.market_regime import MarketRegimeEngine, MarketRegime


class TestMarketRegimeEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MarketRegimeEngine()

    def _create_trending_up_df(self, n=50):
        dates = pd.date_range("2026-08-28 00:00", periods=n, freq="5min")
        base_price = 2650.0
        # Upward price ladder
        closes = [base_price + (i * 0.8) + (np.sin(i) * 0.2) for i in range(n)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.3 for c in closes]
        opens = [c - 0.2 for c in closes]
        vols = [1000 + (i * 10) for i in range(n)]

        return pd.DataFrame({
            "timestamp": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": vols
        })

    def _create_ranging_df(self, n=50):
        dates = pd.date_range("2026-08-28 00:00", periods=n, freq="5min")
        base_price = 2650.0
        # Oscillating tight range
        closes = [base_price + (np.sin(i * 0.5) * 0.4) for i in range(n)]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]
        opens = [c - 0.1 for c in closes]
        vols = [500 for _ in range(n)]

        return pd.DataFrame({
            "timestamp": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": vols
        })

    def test_trending_up_classification(self):
        df = self._create_trending_up_df(60)
        report = self.engine.classify_regime(df)
        self.assertIn(report.regime, [MarketRegime.TRENDING_UP, MarketRegime.BREAKOUT_EXPANSION])
        self.assertGreaterEqual(report.confidence, 60)
        self.assertIn("BULLISH", report.ema_alignment)

    def test_ranging_classification(self):
        df = self._create_ranging_df(60)
        report = self.engine.classify_regime(df)
        self.assertIn(report.regime, [MarketRegime.RANGING, MarketRegime.ROTATIONAL, MarketRegime.UNCLEAR])
        self.assertFalse(report.adx_trending)


if __name__ == "__main__":
    unittest.main()
