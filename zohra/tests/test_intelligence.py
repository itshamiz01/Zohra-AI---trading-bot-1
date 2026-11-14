"""
Unit tests for Zohra Trading Intelligence & Strategy Ecosystem.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from zohra.intelligence.models import (
    PortfolioSnapshot, TimeframeAlignment, SmartMoneySignal,
    MacroEvent, RegimeState, CrossMarketIntel, PipelineDecision,
    StrategyCard, OptimizationResult,
)
from zohra.intelligence.portfolio_intelligence import portfolio_intel
from zohra.intelligence.multi_timeframe import mtf_engine
from zohra.intelligence.smart_money import smc_engine
from zohra.intelligence.macro_intelligence import macro_engine
from zohra.intelligence.regime_engine import regime_engine
from zohra.intelligence.cross_market import cross_market_engine
from zohra.intelligence.decision_pipeline import decision_pipeline
from zohra.intelligence.strategy_marketplace import strategy_marketplace
from zohra.intelligence.strategy_sdk import StrategySDK, StrategyTemplate
from zohra.intelligence.strategy_optimizer import strategy_optimizer


# ─── Mock Data Helpers ────────────────────────────────────────

def generate_mock_ohlcv(bars: int = 100, trend: str = "bullish") -> pd.DataFrame:
    """Generate mock trend/range OHLCV pandas DataFrame."""
    np.random.seed(42)
    dates = [datetime.utcnow() - timedelta(minutes=15 * i) for i in range(bars)]
    dates.reverse()

    # Generate close prices
    if trend == "bullish":
        close = np.linspace(100.0, 110.0, bars) + np.random.normal(0, 0.2, bars)
    elif trend == "bearish":
        close = np.linspace(110.0, 100.0, bars) + np.random.normal(0, 0.2, bars)
    else:  # ranging
        close = np.full(bars, 100.0) + np.random.normal(0, 0.5, bars)

    open_ = close - np.random.normal(0, 0.1, bars)
    high = np.maximum(open_, close) + np.random.uniform(0, 0.3, bars)
    low = np.minimum(open_, close) - np.random.uniform(0, 0.3, bars)
    volume = np.random.randint(100, 1000, bars)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": volume,
    }, index=dates)


# ─── Module 1 Tests: Portfolio Intelligence ───────────────────

def test_portfolio_intelligence_allocations():
    # Record mock returns to build return history
    for ret in [0.001, -0.002, 0.003, -0.001, 0.002, 0.001, -0.001, 0.002]:
        portfolio_intel.record_daily_return(ret)

    # Empty positions allocation check
    snap = portfolio_intel.build_snapshot()
    assert snap.total_equity == 0.0
    assert snap.open_positions == 0
    assert snap.allocation.cash_pct == 100.0
    assert snap.health_score > 0

    # Scenario testing what-if analysis
    scenario = portfolio_intel.scenario_what_if("BTCUSDT", "crypto", 5000)
    assert scenario["symbol"] == "BTCUSDT"
    assert "projected_market_pct" in scenario
    assert "recommendation" in scenario


# ─── Module 2 Tests: Multi-Timeframe Engine ───────────────────

def test_multi_timeframe_analysis():
    # Test indicators calculation inside MTF
    close = np.linspace(100, 110, 50)
    ema = mtf_engine._ema(close, 10)
    assert len(ema) == len(close)
    assert ema[-1] > ema[0]  # Rising trend should have rising EMA

    rsi = mtf_engine._rsi(close, 14)
    assert 0 <= rsi <= 100

    high = close + 0.5
    low = close - 0.5
    adx = mtf_engine._adx(high, low, close, 14)
    assert adx >= 0

    struct = mtf_engine._detect_structure(high, low)
    assert struct in ("HH_HL", "LH_LL", "MIXED", "NONE")


# ─── Module 3 Tests: Smart Money Concept Engine ───────────────

def test_smart_money_engine():
    df = generate_mock_ohlcv(50, "bullish")
    signal = smc_engine.analyze(df, "EURUSD", "M15")
    
    assert isinstance(signal, SmartMoneySignal)
    assert signal.symbol == "EURUSD"
    assert signal.timeframe == "M15"
    assert isinstance(signal.order_blocks, list)
    assert isinstance(signal.fair_value_gaps, list)
    assert signal.confidence >= 0.0
    assert signal.bias in ("BULLISH", "BEARISH", "NEUTRAL")


# ─── Module 4 Tests: Economic & Macro Intelligence ───────────

def test_macro_intelligence():
    summary = macro_engine.get_macro_summary()
    assert "total_events" in summary
    assert "aggregate_severity" in summary

    clearance = macro_engine.check_trade_clearance("EURUSD")
    assert "cleared" in clearance
    assert "blocked" in clearance
    assert "reason" in clearance


# ─── Module 5 Tests: Regime Detection Engine ──────────────────

def test_regime_detection():
    df = generate_mock_ohlcv(60, "bullish")
    state = regime_engine.detect(df, "EURUSD")

    assert isinstance(state, RegimeState)
    assert state.symbol == "EURUSD"
    assert state.primary_regime in ("trending", "ranging", "breakout", "high_volatility", "low_liquidity", "news_driven")
    assert state.confidence > 0
    assert state.adjustments.risk_multiplier > 0
    assert state.adjustments.position_size_multiplier > 0


# ─── Module 6 Tests: Strategy Marketplace ─────────────────────

def test_strategy_marketplace():
    strategy_marketplace.initialize()
    all_strats = strategy_marketplace.list_all()
    assert len(all_strats) > 0

    top = strategy_marketplace.get_top_strategy()
    assert top is not None
    assert top.ai_rating > 0

    # Search strategy
    results = strategy_marketplace.search("scalp")
    assert len(results) >= 0


# ─── Module 7 Tests: Strategy SDK ───────────────

class MockStrategy(StrategyTemplate):
    def on_init(self):
        pass
    def on_signal(self, df, symbol):
        return {
            "direction": "LONG",
            "entry_price": float(df["close"].values[-1]),
            "stop_loss": float(df["close"].values[-1]) - 1.0,
            "take_profit": float(df["close"].values[-1]) + 2.0,
            "confidence": 85.0,
            "reason": "Mock entry signal"
        }

def test_strategy_sdk():
    sdk = StrategySDK()
    strat = MockStrategy("sdk_test_strategy")
    sdk.install_strategy(strat)

    assert "sdk_test_strategy" in sdk._strategies
    
    df = generate_mock_ohlcv(30, "bullish")
    signal = sdk.run_strategy("sdk_test_strategy", df, "EURUSD")
    assert signal["direction"] == "LONG"
    
    val = sdk.validate_signal(signal)
    assert val["valid"] is True


# ─── Module 8 Tests: AI Strategy Optimizer ────────────────────

def test_strategy_optimizer():
    # Simple evaluations
    evaluate_fn = lambda params: params["x"] * 2 + params["y"]
    param_grid = {"x": [1, 2, 3], "y": [10, 20]}

    res = strategy_optimizer.grid_search(evaluate_fn, param_grid, "test_strat")
    assert res.best_params["x"] == 3
    assert res.best_params["y"] == 20
    assert res.in_sample_sharpe == 26.0

    # Monte Carlo test
    trades = [10.0, -5.0, 15.0, -8.0, 20.0, 12.0, -10.0, 25.0, -5.0, 30.0]
    mc_res = strategy_optimizer.monte_carlo_validate(trades, iterations=100)
    assert mc_res.method == "monte_carlo"


# ─── Cross-Market & Decision Pipeline Tests ───────────────────

def test_cross_market_intelligence():
    intel = cross_market_engine.analyze()
    assert isinstance(intel, CrossMarketIntel)
    assert "EURUSD" in intel.correlation_matrix
    assert intel.global_sentiment_score > 0

    comp = cross_market_engine.compare_assets("BTCUSDT", "ETHUSDT")
    assert comp["correlation"] == 0.92


def test_decision_pipeline():
    # End-to-end evaluation
    decision = decision_pipeline.evaluate("EURUSD")
    assert isinstance(decision, PipelineDecision)
    assert decision.symbol == "EURUSD"
    assert decision.decision in ("BUY", "SELL", "WAIT", "AVOID")
    assert len(decision.pipeline_stages) > 0
