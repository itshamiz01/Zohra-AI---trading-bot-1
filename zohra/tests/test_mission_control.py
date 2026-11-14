"""
Unit tests for Zohra Autonomous Trading Mission Control & Self-Healing Engines.
"""

import pytest
from datetime import datetime

from zohra.mission_control.mission_control import mission_control
from zohra.mission_control.self_healing import self_healing_engine
from zohra.mission_control.commander import ai_commander


# ─── Module 1 Tests: Mission Control ─────────────────────────

def test_capital_rotation():
    # Initial weights check
    assert "mt5" in mission_control.allocations
    assert "dhan" in mission_control.allocations

    # Rotate MT5 allocation to 50%
    mission_control.rotate_capital("mt5", 50.0)
    assert mission_control.allocations["mt5"] == 50.0
    
    # Check that sum remains 100
    total = sum(mission_control.allocations.values())
    assert abs(total - 100.0) < 0.01


def test_risk_mode_overrides():
    mission_control.set_risk_mode("defensive")
    assert mission_control.risk_mode == "defensive"

    mission_control.set_risk_mode("moderate")
    assert mission_control.risk_mode == "moderate"


def test_strategy_switching():
    # Verify toggles
    assert "scalping_strategy" in mission_control.strategy_states
    
    ok = mission_control.toggle_strategy("scalping_strategy", False)
    assert ok is True
    assert mission_control.strategy_states["scalping_strategy"] == "inactive"

    mission_control.toggle_strategy("scalping_strategy", True)
    assert mission_control.strategy_states["scalping_strategy"] == "active"


# ─── Module 2 Tests: Self-Healing diagnostics ─────────────────

def test_self_healing_diagnostics():
    res = self_healing_engine.run_diagnostics()
    assert "cpu_usage_pct" in res
    assert "memory_usage_mb" in res
    assert "status" in res
    assert res["status"] in ("NOMINAL", "DEGRADED")


# ─── Module 3 Tests: AI Commander parser ──────────────────────

def test_ai_commander_prompt_nlp():
    # Test emergency stop trigger
    res_stop = ai_commander.process_natural_command("emergency stop")
    assert res_stop["action"] == "emergency_stop"
    assert "EMERGENCY SHUTDOWN" in res_stop["response"]

    # Test diagnostics trigger
    res_diag = ai_commander.process_natural_command("run diagnostics scan")
    assert res_diag["action"] == "diagnostics"
    assert "Diagnostics completed" in res_diag["response"]

    # Test status check
    res_status = ai_commander.process_natural_command("mission control status")
    assert res_status["action"] == "status"
    assert "online" in res_status["response"]
