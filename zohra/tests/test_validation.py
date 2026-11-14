"""
Unit tests for Zohra Professional Trading Validation, Monitoring & Execution Ecosystem.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from zohra.validation.backtester import InstitutionalBacktester
from zohra.validation.paper_engine import paper_engine
from zohra.validation.replay_engine import replay_engine
from zohra.validation.explainability import explainability_engine
from zohra.validation.broker_monitor import broker_monitor
from zohra.validation.audit_system import audit_system


# ─── Mock Data Helpers ────────────────────────────────────────

def generate_mock_ohlcv(bars: int = 100) -> pd.DataFrame:
    """Generate mock stable OHLCV pandas DataFrame."""
    np.random.seed(42)
    dates = [datetime.utcnow() - timedelta(hours=i) for i in range(bars)]
    dates.reverse()

    close = np.linspace(100.0, 105.0, bars) + np.random.normal(0, 0.1, bars)
    open_ = close - np.random.normal(0, 0.05, bars)
    high = np.maximum(open_, close) + np.random.uniform(0, 0.1, bars)
    low = np.minimum(open_, close) - np.random.uniform(0, 0.1, bars)
    volume = np.random.randint(500, 1500, bars)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": volume,
    }, index=dates)


# ─── Module 1 Tests: Backtester ───────────────────────────────

def test_backtester_run_and_mc():
    df = generate_mock_ohlcv(60)
    
    # Simple crossover strategy
    def dummy_strategy(data, idx):
        if idx < 10:
            return None
        close = data["close"].values
        if close[-1] > close[-2] and close[-2] > close[-3]:
            return {"direction": "LONG", "stop_loss": close[-1] * 0.99, "take_profit": close[-1] * 1.02}
        return None

    tester = InstitutionalBacktester(initial_capital=50000.0)
    tester.configure(spread=1.0, slippage=0.2, commission=2.0, latency=50.0)
    
    res = tester.run("EURUSD", df, dummy_strategy, "H1")
    assert res["status"] in ("success", "empty")
    
    if res["status"] == "success":
        assert "net_profit" in res
        assert "sharpe_ratio" in res
        assert len(res["trades"]) >= 0

        # Monte Carlo run
        mc = tester.run_monte_carlo(iterations=50)
        assert "avg_drawdown_pct" in mc
        assert "prob_of_ruin_pct" in mc


# ─── Module 2 Tests: Paper Trading Engine ─────────────────────

def test_paper_engine_lifecycle():
    paper_engine.reset_account(balance=100000.0)
    
    # Place order
    res = paper_engine.place_order("EURUSD", "LONG", 1.0, stop_loss=1.0700, take_profit=1.1000)
    assert res["status"] == "success"
    ticket = res["ticket"]
    
    # Status check
    status = paper_engine.get_portfolio_status()
    assert status["balance"] == 100000.0
    assert len(status["positions"]) == 1
    
    # Close order
    close_res = paper_engine.close_position(ticket, price=1.0900)
    assert close_res["status"] == "success"
    
    # Status after close
    new_status = paper_engine.get_portfolio_status()
    assert len(new_status["positions"]) == 0
    assert len(paper_engine.trade_journal) == 1


# ─── Module 3 Tests: Replay Engine ────────────────────────────

def test_replay_engine_controls():
    ok = replay_engine.load_preset("brexit_vote")
    assert ok is True
    assert replay_engine.symbol == "GBPUSD"
    assert replay_engine.current_idx == 0
    assert replay_engine.is_paused is True

    # Controls
    replay_engine.play()
    assert replay_engine.is_paused is False
    
    replay_engine.pause()
    assert replay_engine.is_paused is True

    bar1 = replay_engine.step_forward()
    assert bar1 is not None
    assert replay_engine.current_idx == 1

    bar0 = replay_engine.step_backward()
    assert bar0 is not None
    assert replay_engine.current_idx == 0


# ─── Module 4 Tests: AI Explainability ────────────────────────

def test_explainability_narrative():
    mock_pipeline = {
        "decision_id": "dec_test_99",
        "symbol": "GBPUSD",
        "decision": "BUY",
        "direction": "LONG",
        "confidence": 88.5,
        "reasons": ["SMC liquidity blocks swept", "Daily bias is strongly bullish"],
        "regime": {"enhanced_regime": "strong_trend", "confidence": 90},
        "mtf_alignment": {"aligned_count": 4, "total_analyzed": 5, "higher_tf_bias": "BULLISH"},
        "smc_signal": {"bias": "BULLISH", "confluence_count": 3},
        "macro_clearance": True
    }

    res = explainability_engine.explain_decision(mock_pipeline)
    assert res["decision_id"] == "dec_test_99"
    assert "Decision Audit for GBPUSD" in res["narrative"]
    assert "SMC liquidity blocks swept" in res["narrative"]

    # Retrieve from db
    saved = explainability_engine.get_explanation("dec_test_99")
    assert saved is not None
    assert saved["decision"] == "BUY"
    assert saved["confidence"] == 88.5


# ─── Module 5 Tests: Broker Health Monitor ────────────────────

def test_broker_health_monitor():
    res = broker_monitor.poll_broker_health("mt5")
    assert res["broker"] == "mt5"
    assert res["status"] in ("online", "offline", "error", "not_configured")
    assert "latency_ms" in res
    assert "health_score" in res


# ─── Module 6 Tests: Trade Replay & Audit ─────────────────────

def test_audit_system():
    opened_at = datetime.utcnow()
    exec_details = {"slippage_pips": 0.2, "latency_ms": 12.5, "broker_response_time": 15}
    ctx = {"regime": "trending", "confidence": 85}

    # Create audit
    record = audit_system.create_audit_record(
        ticket=100099, symbol="XAUUSD", direction="LONG",
        opened_at=opened_at, execution_details=exec_details, context_snapshot=ctx
    )
    assert record["ticket"] == 100099
    assert record["symbol"] == "XAUUSD"

    # Finalize
    closed_at = opened_at + timedelta(minutes=30)
    ok = audit_system.finalize_audit_record(100099, closed_at, 1250.00, "Clean trail exit.")
    assert ok is True

    # Retrieve
    saved = audit_system.get_audit(100099)
    assert saved is not None
    assert saved["pnl"] == 1250.00
    assert saved["lessons_learned"] == "Clean trail exit."
