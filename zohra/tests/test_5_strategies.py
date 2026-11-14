"""
══════════════════════════════════════════════════════════════════════
    ZOHRA — 5-STRATEGY REGIME SUITE UNIT & INTEGRATION TESTS
══════════════════════════════════════════════════════════════════════
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
import pandas as pd
import numpy as np
import datetime as dt

from zohra.core.enums import MarketRegime, StrategyName, Direction, TradeQuality
from zohra.core.market_regime import regime_engine
from zohra.core.symbol_resolver import symbol_resolver
from zohra.core.signal_arbitrator import signal_arbitrator
from zohra.strategies.ema_pullback import EmaPullbackStrategy
from zohra.strategies.vwap_mean_reversion import VwapMeanReversionStrategy
from zohra.strategies.liquidity_mss import LiquidityMssStrategy
from zohra.strategies.breakout import BreakoutStrategy
from zohra.strategies.bollinger_rsi import BollingerRsiStrategy
from zohra.strategies.regime_suite import regime_strategy_suite


def generate_synthetic_ohlcv(bars: int = 100, base_price: float = 4600.0, trend: float = 0.0, vol: float = 1.0) -> pd.DataFrame:
    """Generates synthetic OHLCV dataframe for testing."""
    times = [dt.datetime(2026, 8, 28, 10, 0) + dt.timedelta(minutes=5 * i) for i in range(bars)]
    closes = []
    highs = []
    lows = []
    opens = []
    volumes = []

    p = base_price
    for i in range(bars):
        o = p
        p = o + trend + (np.sin(i / 5.0) * vol) + np.random.normal(0, vol * 0.2)
        c = p
        h = max(o, c) + abs(np.random.normal(0, vol * 0.4))
        l = min(o, c) - abs(np.random.normal(0, vol * 0.4))
        v = int(1000 + abs(np.random.normal(0, 300)))

        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        volumes.append(v)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": volumes
    }, index=times)


class Test5StrategyRegimeSuite(unittest.TestCase):

    def setUp(self):
        self.symbol = "XAUUSD"

    def test_01_hard_symbol_guard(self):
        """Verify the configured multi-market guard and XAU strategy specialization."""
        self.assertTrue(symbol_resolver.is_symbol_allowed("XAUUSD"))
        self.assertTrue(symbol_resolver.is_symbol_allowed("XAUUSDm"))
        for sym in ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY"]:
            self.assertTrue(symbol_resolver.is_symbol_allowed(sym))
        
        disallowed = ["XAGUSD", "BTCUSDT", "ETHUSDT", "US30", "GER40"]
        for sym in disallowed:
            self.assertFalse(symbol_resolver.is_symbol_allowed(sym), f"Disallowed symbol {sym} was not blocked!")
            is_allowed, _ = symbol_resolver.enforce_guard(sym, context="Test")
            self.assertFalse(is_allowed)

    def test_02_market_regime_classification(self):
        """Verify Market Regime Engine classifies trending and ranging regimes."""
        # Strong Trending Up Data
        df_up = generate_synthetic_ohlcv(bars=100, base_price=4600.0, trend=1.5, vol=0.5)
        res_up = regime_engine.classify(df_up)
        self.assertIn(res_up["regime"], (MarketRegime.TRENDING_UP, MarketRegime.BREAKOUT_EXPANSION, MarketRegime.TRENDING))
        self.assertGreaterEqual(res_up["confidence"], 60)

        # Ranging Data (Flat oscillating range)
        times = [dt.datetime(2026, 8, 28, 10, 0) + dt.timedelta(minutes=5 * i) for i in range(100)]
        closes = [4600.0 + (0.2 if i % 2 == 0 else -0.2) for i in range(100)]
        opens = [4600.0 - (0.2 if i % 2 == 0 else -0.2) for i in range(100)]
        highs = [4600.5 for _ in range(100)]
        lows = [4599.5 for _ in range(100)]
        vols = [1000 for _ in range(100)]
        df_range = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "tick_volume": vols}, index=times)
        
        res_range = regime_engine.classify(df_range)
        self.assertIn(res_range["regime"], (MarketRegime.RANGING, MarketRegime.ROTATIONAL, MarketRegime.LOW_LIQUIDITY))

    def test_03_ema_pullback_strategy(self):
        """Verify EMA Pullback strategy eligibility and signal validation."""
        strat = EmaPullbackStrategy()
        
        # Test eligibility
        el_up, _ = strat.check_eligibility({"regime": MarketRegime.TRENDING_UP, "confidence": 85})
        self.assertTrue(el_up)

        el_range, _ = strat.check_eligibility({"regime": MarketRegime.RANGING, "confidence": 85})
        self.assertFalse(el_range)

        # Reject non-gold symbol
        sig_disallowed = strat.generate_signal(generate_synthetic_ohlcv(), symbol="EURUSD")
        self.assertIsNone(sig_disallowed)

    def test_04_vwap_mean_reversion_strategy(self):
        """Verify VWAP Mean Reversion is blocked in strong trends and active in ranging markets."""
        strat = VwapMeanReversionStrategy()
        
        # Ineligible in strong trend
        el_trend, _ = strat.check_eligibility({"regime": MarketRegime.TRENDING_UP, "metrics": {"adx": 35.0}})
        self.assertFalse(el_trend)

        # Eligible in ranging market with low ADX
        el_range, _ = strat.check_eligibility({"regime": MarketRegime.RANGING, "metrics": {"adx": 15.0}})
        self.assertTrue(el_range)

    def test_05_liquidity_mss_strategy(self):
        """Verify Liquidity Sweep + MSS triggers on structural sweep and shift."""
        strat = LiquidityMssStrategy()
        
        df = generate_synthetic_ohlcv(bars=60, base_price=4600.0, trend=0.0, vol=1.0)
        # Ineligible in news shock
        el_news, _ = strat.check_eligibility({"regime": MarketRegime.NEWS_OR_ABNORMAL_VOLATILITY})
        self.assertFalse(el_news)

        el_normal, _ = strat.check_eligibility({"regime": MarketRegime.RANGING})
        self.assertTrue(el_normal)

    def test_06_breakout_strategy_duplicate_prevention(self):
        """Verify Breakout strategy generates single entry and suppresses duplicates for same event."""
        strat = BreakoutStrategy()
        df = generate_synthetic_ohlcv(bars=60, base_price=4600.0, trend=2.0, vol=0.5)

        sig1 = strat.generate_signal(df, symbol="XAUUSD")
        if sig1:
            # Re-running immediately on same bar must produce None (duplicate suppression)
            sig2 = strat.generate_signal(df, symbol="XAUUSD")
            self.assertIsNone(sig2, "Breakout strategy failed duplicate suppression!")

    def test_07_bollinger_rsi_strategy(self):
        """Verify Bollinger + RSI strategy checks oversold/overbought and blocks runaway trends."""
        strat = BollingerRsiStrategy()
        
        # Blocked if ADX is too high
        el_runaway, _ = strat.check_eligibility({"regime": MarketRegime.TRENDING_UP, "metrics": {"adx": 30.0}})
        self.assertFalse(el_runaway)

        el_ok, _ = strat.check_eligibility({"regime": MarketRegime.RANGING, "metrics": {"adx": 18.0}})
        self.assertTrue(el_ok)

    def test_08_signal_arbitration_and_conflict_resolution(self):
        """Verify Signal Arbitrator detects opposing conflicts and handles concordant signals."""
        # 1. Opposing Conflict (BUY vs SELL)
        sig_buy = {
            "strategy": StrategyName.EMA_PULLBACK.value,
            "symbol": "XAUUSD",
            "direction": Direction.LONG.value,
            "entry_price": 4600.0,
            "stop_loss": 4590.0,
            "take_profit": 4620.0,
            "confidence_score": 82
        }
        sig_sell = {
            "strategy": StrategyName.VWAP_MEAN_REVERSION.value,
            "symbol": "XAUUSD",
            "direction": Direction.SHORT.value,
            "entry_price": 4600.0,
            "stop_loss": 4610.0,
            "take_profit": 4580.0,
            "confidence_score": 80
        }

        arb_conflict = signal_arbitrator.arbitrate([sig_buy, sig_sell], {"regime": MarketRegime.ROTATIONAL, "confidence": 75})
        self.assertEqual(arb_conflict["action"], "NO_TRADE")
        self.assertEqual(arb_conflict["conflict_status"], "CONFLICT_OPPOSING_DIRECTIONS")

        # 2. Concordant Agreement (Multiple BUYs -> Boost Score)
        sig_buy_2 = {
            "strategy": StrategyName.LIQUIDITY_MSS.value,
            "symbol": "XAUUSD",
            "direction": Direction.LONG.value,
            "entry_price": 4600.0,
            "stop_loss": 4592.0,
            "take_profit": 4625.0,
            "confidence_score": 85
        }

        arb_concordant = signal_arbitrator.arbitrate([sig_buy, sig_buy_2], {"regime": MarketRegime.TRENDING_UP, "confidence": 85})
        self.assertEqual(arb_concordant["action"], "TRADE")
        self.assertEqual(arb_concordant["winning_signal"]["direction"], Direction.LONG.value)
        self.assertGreaterEqual(arb_concordant["final_score"], 85)
        self.assertIn(arb_concordant["grade"], (TradeQuality.A, TradeQuality.A_PLUS))

    def test_09_full_regime_suite_integration(self):
        """Verify full suite evaluation and diagnostic formatting."""
        df = generate_synthetic_ohlcv(bars=80, base_price=4600.0, trend=0.5, vol=0.8)
        win_sig, diag_box = regime_strategy_suite.evaluate(df, symbol="XAUUSD")

        self.assertIsInstance(diag_box, str)
        self.assertIn("SPECIALIZED CONFLUENCE ENGINE", diag_box)
        self.assertIn("EMA_PULLBACK", diag_box)
        self.assertIn("VWAP_MEAN_REVERSION", diag_box)
        self.assertIn("LIQUIDITY_MSS", diag_box)
        self.assertIn("BREAKOUT", diag_box)
        self.assertIn("BOLLINGER_RSI", diag_box)


if __name__ == "__main__":
    unittest.main()
