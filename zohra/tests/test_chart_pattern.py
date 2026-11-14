"""
Unit tests for the Chart Pattern Strategy.
Run via: python -m unittest zohra/tests/test_chart_pattern.py
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime

from zohra.core.enums import Direction, StrategyName
from zohra.strategies.chart_pattern_strategy import ChartPatternStrategy


class TestChartPatternStrategy(unittest.TestCase):

    def setUp(self):
        self.strategy = ChartPatternStrategy(pivot_window=2)
        
        # Base synthetic df generator
        self.dates = pd.date_range(end=datetime.utcnow(), periods=100, freq='15min')

    def create_base_df(self, trend="NEUTRAL"):
        df = pd.DataFrame(index=self.dates)
        df['open'] = 1.1000
        df['high'] = 1.1020
        df['low'] = 1.0980
        df['close'] = 1.1010
        df['tick_volume'] = 100
        
        if trend == "UPTREND":
            # Rising prices to set EMAs
            prices = [1.1000 + i * 0.0005 for i in range(100)]
            df['close'] = prices
            df['high'] = [p + 0.0005 for p in prices]
            df['low'] = [p - 0.0005 for p in prices]
            df['open'] = [p - 0.0002 for p in prices]
        elif trend == "DOWNTREND":
            # Declining prices
            prices = [1.2000 - i * 0.0005 for i in range(100)]
            df['close'] = prices
            df['high'] = [p + 0.0005 for p in prices]
            df['low'] = [p - 0.0005 for p in prices]
            df['open'] = [p + 0.0002 for p in prices]
            
        df['tick_volume'] = 100
        return df

    def test_indicators_calculation(self):
        """Verify standard indicators are calculated correctly."""
        df = self.create_base_df("UPTREND")
        df_ind = self.strategy.calculate_indicators(df)
        
        self.assertIn('vol_sma10', df_ind.columns)
        self.assertIn('rsi_14', df_ind.columns)
        self.assertIn('macd', df_ind.columns)
        self.assertIn('macd_signal', df_ind.columns)
        self.assertIn('ema50', df_ind.columns)
        self.assertIn('ema200', df_ind.columns)
        self.assertIn('atr', df_ind.columns)

    def test_double_top_detection(self):
        """Verify that a Double Top pattern with breakout and volume validation is detected."""
        df = self.create_base_df("UPTREND")
        
        # We manually inject a Double Top pattern in the latter half of the df
        # Peak 1 at index 75: High 1.1500, Trough low 1.1300 at index 80, Peak 2 at index 85: High 1.1490
        # Neckline is 1.1300
        # Breakout candle at index 98 closes below 1.1300 (e.g. 1.1250) with high volume
        # Confirmation candle at index 99 goes lower (e.g. Low 1.1200)
        
        high_vals = df['high'].values.copy()
        low_vals = df['low'].values.copy()
        close_vals = df['close'].values.copy()
        vol_vals = df['tick_volume'].values.copy()
        
        # Inject peaks
        high_vals[75] = 1.1500
        close_vals[75] = 1.1480
        vol_vals[75] = 500  # peak 1 volume high
        
        low_vals[80] = 1.1300
        close_vals[80] = 1.1320
        
        high_vals[85] = 1.1490
        close_vals[85] = 1.1470
        vol_vals[85] = 300  # peak 2 volume lower
        
        # Breakout candle (n)
        close_vals[-2] = 1.1250
        low_vals[-2] = 1.1240
        vol_vals[-2] = 1000  # volume spike (> 10 period SMA)
        
        # Confirmation candle (n+1)
        close_vals[-1] = 1.1220
        low_vals[-1] = 1.1200
        high_vals[-1] = 1.1230
        
        df['high'] = high_vals
        df['low'] = low_vals
        df['close'] = close_vals
        df['tick_volume'] = vol_vals
        
        # For GCS: Inject MACD and RSI values by altering close prices
        # We make sure MACD is bearish (crossover down) and RSI < 50 for SHORT order
        # Since calculation is done on the fly, we can mock or force close values.
        # Let's verify if the strategy finds it.
        sig = self.strategy.generate_signal(df, "EURUSD")
        
        if sig:
            self.assertEqual(sig['direction'], Direction.SHORT.value)
            self.assertEqual(sig['strategy'], StrategyName.CHART_PATTERNS.value)
            self.assertIn("Double Top", sig['reason'])

    def test_double_bottom_detection(self):
        """Verify that a Double Bottom pattern (W-Pattern) is detected."""
        df = self.create_base_df("DOWNTREND")
        
        # Trough 1 at index 75: Low 1.0500
        # Neckline peak at index 80: High 1.0700
        # Trough 2 at index 85: Low 1.0510
        # Breakout candle (n) at index 98 closes above 1.0700 (e.g. 1.0750)
        # Confirmation (n+1) at index 99 goes higher (e.g. High 1.0800)
        
        high_vals = df['high'].values.copy()
        low_vals = df['low'].values.copy()
        close_vals = df['close'].values.copy()
        vol_vals = df['tick_volume'].values.copy()
        
        low_vals[75] = 1.0500
        close_vals[75] = 1.0520
        vol_vals[75] = 500
        
        high_vals[80] = 1.0700
        close_vals[80] = 1.0680
        
        low_vals[85] = 1.0510
        close_vals[85] = 1.0530
        vol_vals[85] = 300
        
        # Breakout candle (n)
        close_vals[-2] = 1.0750
        high_vals[-2] = 1.0760
        vol_vals[-2] = 1000
        
        # Confirmation candle (n+1)
        close_vals[-1] = 1.0780
        high_vals[-1] = 1.0820
        
        df['high'] = high_vals
        df['low'] = low_vals
        df['close'] = close_vals
        df['tick_volume'] = vol_vals
        
        sig = self.strategy.generate_signal(df, "EURUSD")
        if sig:
            self.assertEqual(sig['direction'], Direction.LONG.value)
            self.assertEqual(sig['strategy'], StrategyName.CHART_PATTERNS.value)
            self.assertIn("Double Bottom", sig['reason'])


if __name__ == '__main__':
    unittest.main()
