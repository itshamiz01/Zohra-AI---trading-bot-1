"""Regression coverage for analysis values that previously used invented defaults."""
import sqlite3
from unittest.mock import patch

import pytest

from zohra.analytics.advanced_analytics import AdvancedAnalyticsManager


@pytest.fixture
def analytics_store(tmp_path):
    path = tmp_path / "analytics.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE trades (strategy_used TEXT, pnl_usd REAL, timestamp_close TEXT);
            CREATE TABLE execution_metrics (execution_delay_ms REAL, latency_ms REAL,
                spread_at_entry REAL, slippage_points REAL);
        """)
    manager = AdvancedAnalyticsManager()
    manager.db_path = str(path)
    return manager, path


def test_timeframe_win_rates_use_recorded_outcomes(analytics_store):
    manager, path = analytics_store
    with sqlite3.connect(path) as conn:
        conn.executemany("INSERT INTO trades VALUES (?, ?, ?)", [
            ("scalp_m15", 2, "2026-01-01"), ("scalp_m15", -1, "2026-01-02"),
            ("scalp_m1", 3, "2026-01-01"),
        ])
    stats = manager.get_timeframe_performance()
    assert stats["M15"]["win_rate"] == 50
    assert stats["M15"]["trades"] == 2
    assert stats["M1"]["win_rate"] == 100


def test_empty_broker_metrics_and_monte_carlo_are_unavailable(analytics_store):
    manager, _ = analytics_store
    assert all(value is None for value in manager.get_broker_performance().values())
    result = manager.run_monte_carlo_analysis()
    assert result["status"] == "insufficient_data"
    assert result["sample_paths"] == []


def test_recorded_zero_broker_metrics_are_preserved(analytics_store):
    manager, path = analytics_store
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO execution_metrics VALUES (0, 0, 0, 0)")
    result = manager.get_broker_performance()
    assert result["execution_delay_ms"] == 0
    assert result["average_slippage_points"] == 0


def test_no_random_correlation_when_broker_is_offline():
    with patch("zohra.analytics.advanced_analytics.mt5", None):
        result = AdvancedAnalyticsManager().get_correlations()
    assert result["status"] == "unavailable"
    assert result["matrix"] == {}


def test_unavailable_mission_data_cannot_approve_trade():
    from zohra.mission_control.decision_engine import decision_engine
    with patch("zohra.mission_control.cross_market.cross_market_intel.analyze_global_market",
               return_value={"status": "unavailable", "sentiment": "UNKNOWN", "risk_index": None}), \
         patch("zohra.mission_control.portfolio_intel.portfolio_intel.evaluate_portfolio",
               return_value={"status": "unavailable", "unified_portfolio_score": None}), \
         patch("zohra.intelligence.decision_pipeline.decision_pipeline.get_all_decisions", return_value={}):
        assert decision_engine.execute_decision_cycle("BTCUSDT")["approved"] is False


@pytest.mark.parametrize("sql", [
    "DELETE FROM trades", "DROP TABLE trades", "PRAGMA user_version = 1",
    "ATTACH DATABASE ':memory:' AS extra", "SELECT * FROM sqlite_master",
    "SELECT load_extension('anything')", "SELECT randomblob(1000000000)",
    "SELECT * FROM trades; DELETE FROM trades",
])
def test_model_sql_cannot_modify_or_read_outside_reporting_tables(analytics_store, sql):
    manager, path = analytics_store
    with pytest.raises(sqlite3.DatabaseError):
        manager._read_analysis_query(sql)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM trades").fetchone()[0] == 0


def test_model_sql_accepts_reporting_aggregates(analytics_store):
    manager, path = analytics_store
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO trades VALUES ('m15', 12, '2026-01-01')")
    assert manager._read_analysis_query("SELECT COUNT(*) AS n, SUM(pnl_usd) AS pnl FROM trades") == [{"n": 1, "pnl": 12}]


def test_risk_simulator_preserves_stop_loss_and_full_baseline(tmp_path):
    path = tmp_path / 'scenario.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE trades (symbol TEXT, pnl_usd REAL, timestamp_close TEXT)')
        conn.executemany('INSERT INTO trades VALUES (?, ?, ?)', [
            ('EURUSD', 100, '2026-01-03'), ('EURUSD', -90, '2026-01-02'), ('EURUSD', 20, '2026-01-01')])
    manager = AdvancedAnalyticsManager()
    manager.db_path = str(path)
    result = manager.simulate_risk_scenarios()
    assert result['original_net_profit'] == 30
    assert result['simulated_net_profit'] == -70
    assert result['ending_equity'] == 80
    assert result['simulated_trades'] == 2
    assert result['original_drawdown_pct'] == pytest.approx(90 / 170 * 100, abs=0.01)
    assert result['simulated_drawdown_pct'] == result['original_drawdown_pct']
    assert result['margin_level_impact'] is None


@pytest.mark.parametrize('lot_mult,stop_equity', [(0, 100), (float('nan'), 100), (1, 150), (1, -10)])
def test_risk_simulator_rejects_invalid_assumptions(lot_mult, stop_equity):
    with pytest.raises(ValueError):
        AdvancedAnalyticsManager().simulate_risk_scenarios(lot_mult, stop_equity)
