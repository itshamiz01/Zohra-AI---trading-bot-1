"""
Unit tests for the expanded Zohra Autonomous Trading Platform modules.
"""

import pytest
from unittest.mock import patch
import numpy as np

from zohra.mission_control.cross_market import cross_market_intel
from zohra.mission_control.portfolio_intel import portfolio_intel
from zohra.mission_control.capital_rotation import capital_rotation_engine
from zohra.mission_control.opportunity_ranker import opportunity_ranker
from zohra.mission_control.correlation_engine import correlation_engine
from zohra.mission_control.risk_manager import risk_manager
from zohra.mission_control.capital_allocator import capital_allocator
from zohra.mission_control.strategy_switcher import strategy_switcher
from zohra.mission_control.optimization_loop import optimization_loop
from zohra.mission_control.decision_engine import decision_engine


def test_cross_market_engine():
    with patch("zohra.intelligence.cross_market.cross_market_engine._fetch_live_prices", return_value={}):
        res = cross_market_intel.analyze_global_market()
    assert res["status"] == "unavailable"
    assert res["risk_index"] is None
    with patch("zohra.intelligence.cross_market.cross_market_engine._fetch_live_prices",
               return_value={"BTCUSDT": np.linspace(100, 110, 20)}):
        res = cross_market_intel.analyze_global_market()
    assert res["status"] == "success"
    assert res["risk_index"] > 50


def test_portfolio_intelligence():
    with patch("zohra.brokers.manager.broker_manager.get_registered_brokers", return_value=[]):
        res = portfolio_intel.evaluate_portfolio()
    assert res["status"] == "unavailable"
    assert res["unified_portfolio_score"] is None
    assert res["diversification_index"] is None


def test_capital_rotation_computation():
    weights = capital_rotation_engine.compute_rotation_matrix("RISK_OFF", 85.0)
    assert weights["cash"] == 35.0
    assert weights["coindcx"] == 10.0


def test_opportunity_ranking_engine():
    with patch("zohra.intelligence.decision_pipeline.decision_pipeline.get_all_decisions", return_value={}):
        assert opportunity_ranker.rank_opportunities() == []
    decisions = {"EURUSD": {"decision": "BUY", "confidence": 75},
                 "XAUUSD": {"decision": "SELL", "confidence": 88}}
    with patch("zohra.intelligence.decision_pipeline.decision_pipeline.get_all_decisions", return_value=decisions):
        opps = opportunity_ranker.rank_opportunities()
    assert [op["symbol"] for op in opps] == ["XAUUSD", "EURUSD"]


def test_correlation_engine():
    with patch("zohra.intelligence.cross_market.cross_market_engine._fetch_live_prices", return_value={}):
        assert correlation_engine.compute_correlation_matrix() == {}
    history = {"XAUUSD": np.geomspace(100, 150, 20) + np.arange(20) ** 2,
               "BTCUSDT": np.geomspace(100, 150, 20) + np.arange(20) ** 2}
    with patch("zohra.intelligence.cross_market.cross_market_engine._fetch_live_prices", return_value=history):
        matrix = correlation_engine.compute_correlation_matrix()
    assert matrix["XAUUSD"]["BTCUSDT"] == 1.0


def test_autonomous_risk_management():
    res = risk_manager.adjust_risk_parameters("defensive", 30.0)
    assert res["risk_multiplier"] == 0.5
    assert res["daily_loss_limit_pct"] == 1.5


def test_autonomous_capital_allocator():
    alloc = capital_allocator.allocate_capital({}, "strong_trend")
    assert alloc["coindcx"] == 30.0
    assert alloc["cash"] == 0.0


def test_autonomous_strategy_switching():
    states = strategy_switcher.evaluate_strategies("high_volatility", 6.2)
    assert states["scalping_strategy"] == "inactive"
    assert states["mean_reversion"] == "active"


def test_continuous_ai_optimization():
    before = optimization_loop.optimizations_count
    with patch("zohra.learning.walk_forward_optimizer.walk_forward_optimizer.run_optimization_cycle",
               return_value={"status": "skipped", "reason": "Insufficient trades"}):
        res = optimization_loop.trigger_parameter_sweep()
    assert res["status"] == "skipped"
    assert res["optimizations_count"] == before
    assert res["adjustments"] == {}
    assert res["applied"] is False
    with patch("zohra.learning.walk_forward_optimizer.walk_forward_optimizer.run_optimization_cycle",
               return_value={"status": "success", "best_weights": {"structure": 0.2}}):
        res = optimization_loop.trigger_parameter_sweep()
    assert res["best_weights"] == {"structure": 0.2}
    assert res["optimizations_count"] == before + 1
    assert res["applied"] is False


def test_autonomous_decision_engine_cycle():
    res = decision_engine.execute_decision_cycle("BTCUSDT")
    assert "approved" in res
    assert "pipeline_context" in res
    assert "risk_index" in res["pipeline_context"]
