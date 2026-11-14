import unittest
from datetime import datetime
from zohra.brokers.sim_broker import SimBroker

class TestSimulatedBroker(unittest.TestCase):

    def setUp(self):
        self.broker = SimBroker(initial_balance=10000.0)

    def test_broker_initialization(self):
        """Verify broker starts with the correct balance and equity."""
        self.assertEqual(self.broker.get_balance(), 10000.0)
        self.assertEqual(self.broker.get_equity(), 10000.0)
        self.assertTrue(self.broker.is_connected())

    def test_open_and_close_trade(self):
        """Verify opening and closing simulated trades works and impacts balance."""
        # Set current tick price
        self.broker.set_tick("EURUSD", 1.1000, 1.1002) # Bid 1.1000, Ask 1.1002
        
        # Open LONG trade: Entry is Ask price (1.1002)
        pos = self.broker.open_trade(
            symbol="EURUSD",
            direction="LONG",
            lots=0.1,
            stop_loss=1.0950,
            take_profit=1.1100
        )
        self.assertIsNotNone(pos)
        self.assertEqual(pos["entry_price"], 1.1002)
        self.assertEqual(len(self.broker.get_open_positions()), 1)

        # Move price up to 1.1052 bid / 1.1054 ask (profit zone)
        self.broker.set_tick("EURUSD", 1.1052, 1.1054)
        
        # Close LONG trade: Exit is Bid price (1.1052)
        # PnL: (1.1052 - 1.1002) * 100,000 * 0.1 lots = 0.0050 * 10,000 = $50.0
        res = self.broker.close_trade(pos["ticket"], "EURUSD", "LONG")
        self.assertIsNotNone(res)
        self.assertTrue(res["success"])
        self.assertEqual(res["pnl"], 50.0)
        self.assertEqual(self.broker.get_balance(), 10050.0)
        self.assertEqual(len(self.broker.get_open_positions()), 0)

    def test_trade_modifications(self):
        """Verify modifying open trade SL and TP properties."""
        self.broker.set_tick("EURUSD", 1.1000, 1.1002)
        pos = self.broker.open_trade("EURUSD", "LONG", 0.1, 1.0950, 1.1100)
        
        modified = self.broker.modify_trade(pos["ticket"], new_sl=1.0980, new_tp=1.1200)
        self.assertTrue(modified)
        
        open_pos = self.broker.get_open_positions(symbol="EURUSD")[0]
        self.assertEqual(open_pos["stop_loss"], 1.0980)
        self.assertEqual(open_pos["take_profit"], 1.1200)

    def test_stop_loss_hit(self):
        """Verify position closes when bid price breaks SL."""
        self.broker.set_tick("EURUSD", 1.1000, 1.1002)
        pos = self.broker.open_trade("EURUSD", "LONG", 0.1, 1.0950, 1.1100)
        
        # Move price down to break SL (1.0948 bid)
        self.broker.set_tick("EURUSD", 1.0948, 1.0950)
        self.broker.check_sl_tp_fills()
        
        self.assertEqual(len(self.broker.get_open_positions()), 0)
        self.assertEqual(len(self.broker.closed_trades_history), 1)
        self.assertEqual(self.broker.closed_trades_history[0]["comment"], "SL_HIT")

    def test_take_profit_hit(self):
        """Verify position closes when bid price breaks TP."""
        self.broker.set_tick("EURUSD", 1.1000, 1.1002)
        pos = self.broker.open_trade("EURUSD", "LONG", 0.1, 1.0950, 1.1100)
        
        # Move price up to break TP (1.1102 bid)
        self.broker.set_tick("EURUSD", 1.1102, 1.1104)
        self.broker.check_sl_tp_fills()
        
        self.assertEqual(len(self.broker.get_open_positions()), 0)
        self.assertEqual(len(self.broker.closed_trades_history), 1)
        self.assertEqual(self.broker.closed_trades_history[0]["comment"], "TP_HIT")

if __name__ == "__main__":
    unittest.main()
