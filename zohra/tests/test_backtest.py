import unittest
from datetime import datetime
import pandas as pd
from unittest.mock import patch, MagicMock

from zohra.core.backtest import BacktestEngine
from zohra.core.enums import MarketRegime, StrategyName

class TestBacktestingEngine(unittest.TestCase):

    def setUp(self):
        # Create synthetic datasets of 150 bars for H1, M15, M5
        dates_m15 = pd.date_range(end=datetime.utcnow(), periods=150, freq='15min')
        dates_m5 = pd.date_range(end=datetime.utcnow(), periods=150, freq='5min')
        dates_h1 = pd.date_range(end=datetime.utcnow(), periods=150, freq='h')

        self.df_m15 = pd.DataFrame(index=dates_m15)
        self.df_m15['open'] = 1.1000
        self.df_m15['high'] = 1.1020
        self.df_m15['low'] = 1.0980
        self.df_m15['close'] = 1.1010
        self.df_m15['tick_volume'] = 1000
        self.df_m15['real_volume'] = 1000
        self.df_m15['atr'] = 0.0020

        self.df_m5 = pd.DataFrame(index=dates_m5)
        self.df_m5['open'] = 1.1000
        self.df_m5['high'] = 1.1010
        self.df_m5['low'] = 1.0990
        self.df_m5['close'] = 1.1005
        self.df_m5['tick_volume'] = 500
        self.df_m5['real_volume'] = 500
        self.df_m5['atr'] = 0.0010

        self.df_h1 = pd.DataFrame(index=dates_h1)
        self.df_h1['open'] = 1.1000
        self.df_h1['high'] = 1.1050
        self.df_h1['low'] = 1.0950
        self.df_h1['close'] = 1.1020
        self.df_h1['tick_volume'] = 4000
        self.df_h1['real_volume'] = 4000
        self.df_h1['atr'] = 0.0050

    @patch('zohra.agents.market_analysis_agent.decision_engine')
    @patch('zohra.db.schema.db._execute')
    def test_backtest_execution(self, mock_db_execute, mock_dec_engine):
        """Verify backtest loops step-by-step, executes fills, and generates reports."""
        engine = BacktestEngine(initial_balance=10000.0, min_score_threshold=70)
        
        # Mock decision engine to generate a BUY setup at bar index 110
        mock_explanation = MagicMock()
        mock_explanation.strategy_used = StrategyName.TREND_FOLLOWING.value
        mock_explanation.decision = "BUY"
        mock_explanation.confidence_score = 85
        mock_explanation.entry_price = 1.1010
        mock_explanation.stop_loss = 1.0960
        mock_explanation.take_profit = 1.1110
        mock_explanation.regime = MarketRegime.TRENDING.value
        mock_explanation.summary_reason = "Bullish trend setup"
        mock_explanation.scores_breakdown = {"structure": 90, "smc": 80}
        mock_explanation.agreed_modules = ["structure", "smc"]
        mock_explanation.disagreed_modules = []
        mock_explanation.to_dict.return_value = {}

        # Set side effect: trigger setup at specific lookback index
        def dec_engine_side_effect(df_m5, df_m15, df_h1, symbol):
            if len(df_m15) == 111:
                return mock_explanation
            empty_exp = MagicMock()
            empty_exp.strategy_used = "none"
            empty_exp.decision = "WAIT"
            return empty_exp

        mock_dec_engine.process_data.side_effect = dec_engine_side_effect
        mock_db_execute.return_value = []

        # Run backtest
        report = engine.run_backtest(
            df_m5=self.df_m5,
            df_m15=self.df_m15,
            df_h1=self.df_h1,
            symbol="EURUSD",
            start_idx=100
        )

        # Confirm backtest report generated
        self.assertIsNotNone(report)
        self.assertEqual(report["total_trades"], 1)
        self.assertEqual(report["winning_trades"], 0)
        self.assertEqual(len(engine.sim_broker.closed_trades_history), 1)

if __name__ == "__main__":
    unittest.main()
