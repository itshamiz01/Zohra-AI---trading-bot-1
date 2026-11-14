"""
╔══════════════════════════════════════════════════════════════════════╗
║        ZOHRA — MULTI-BOT SPECIALIZATION & CORRELATION TESTS          ║
║      Automated Unit Tests & 4-Scenario Market Simulation Suite       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import datetime as dt
from pathlib import Path

from zohra.config.bot_profile import (
    BOT_1_TREND_PROFILE,
    BOT_2_REVERSAL_PROFILE,
    BOT_3_STRUCTURE_PROFILE,
    load_bot_profile
)
from zohra.core.enums import MarketRegime, StrategyName, StrategyGroup
from zohra.core.market_regime import RegimeReport
from zohra.core.strategy_fingerprint import StrategyFingerprint, build_strategy_fingerprint
from zohra.core.cross_bot_signal_registry import CrossBotSignalRegistry
from zohra.core.portfolio_risk_coordinator import PortfolioRiskCoordinator


# ════════════════════════════════════════════════════════════════════════
#  1. UNIT TESTS: BOT PROFILES & SPECIALIZATION ISOLATION
# ════════════════════════════════════════════════════════════════════════

def test_bot_profiles_strategy_isolation():
    """Verify that the three bot profiles are specialized into distinct strategy groups."""
    # Bot 1 must only have Trend strategies
    assert StrategyName.EMA_PULLBACK.value in BOT_1_TREND_PROFILE.enabled_strategies
    assert StrategyName.FIBONACCI_PULLBACK.value in BOT_1_TREND_PROFILE.enabled_strategies
    assert StrategyName.VWAP_MEAN_REVERSION.value not in BOT_1_TREND_PROFILE.enabled_strategies
    assert StrategyName.LIQUIDITY_MSS.value not in BOT_1_TREND_PROFILE.enabled_strategies

    # Bot 2 must only have Mean Reversion strategies
    assert StrategyName.VWAP_MEAN_REVERSION.value in BOT_2_REVERSAL_PROFILE.enabled_strategies
    assert StrategyName.BOLLINGER_RSI.value in BOT_2_REVERSAL_PROFILE.enabled_strategies
    assert StrategyName.EMA_PULLBACK.value not in BOT_2_REVERSAL_PROFILE.enabled_strategies
    assert StrategyName.BREAKOUT.value not in BOT_2_REVERSAL_PROFILE.enabled_strategies

    # Bot 3 must have Structure & Breakout strategies
    assert StrategyName.LIQUIDITY_MSS.value in BOT_3_STRUCTURE_PROFILE.enabled_strategies
    assert StrategyName.BREAKOUT.value in BOT_3_STRUCTURE_PROFILE.enabled_strategies
    assert StrategyName.EMA_PULLBACK.value not in BOT_3_STRUCTURE_PROFILE.enabled_strategies
    assert StrategyName.BOLLINGER_RSI.value not in BOT_3_STRUCTURE_PROFILE.enabled_strategies


def test_bot_profiles_regime_tradability():
    """Verify regime prioritization and blocking per bot role."""
    # Bot 1 (Trend Specialist)
    assert BOT_1_TREND_PROFILE.get_regime_priority("trending_up") == "HIGH"
    assert BOT_1_TREND_PROFILE.get_regime_priority("ranging") == "BLOCKED"
    assert BOT_1_TREND_PROFILE.is_regime_tradable("trending_up") is True
    assert BOT_1_TREND_PROFILE.is_regime_tradable("ranging") is False

    # Bot 2 (Reversal Specialist)
    assert BOT_2_REVERSAL_PROFILE.get_regime_priority("ranging") == "HIGH"
    assert BOT_2_REVERSAL_PROFILE.get_regime_priority("trending_up") == "BLOCKED"
    assert BOT_2_REVERSAL_PROFILE.is_regime_tradable("ranging") is True
    assert BOT_2_REVERSAL_PROFILE.is_regime_tradable("trending_up") is False

    # Bot 3 (Structure/Breakout Specialist)
    assert BOT_3_STRUCTURE_PROFILE.get_regime_priority("breakout_expansion") == "HIGH"
    assert BOT_3_STRUCTURE_PROFILE.get_regime_priority("structural_transition") == "HIGH"
    assert BOT_3_STRUCTURE_PROFILE.is_regime_tradable("breakout_expansion") is True


# ════════════════════════════════════════════════════════════════════════
#  2. UNIT TESTS: DUPLICATE EXPOSURE SCORING (0-100)
# ════════════════════════════════════════════════════════════════════════

def test_duplicate_exposure_scoring(tmp_path):
    """Verify exact 0-100 duplicate exposure point formula."""
    registry = CrossBotSignalRegistry(shared_dir=str(tmp_path))

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    # Base signal from Bot 1
    sig1 = StrategyFingerprint(
        signal_id="SIG_TEST_1",
        bot_id="BOT_1_TREND",
        bot_name="Bot A",
        bot_role="Trend & Momentum Specialist",
        symbol="XAUUSD",
        direction="BUY",
        strategy_name="EMA_PULLBACK",
        strategy_group="TREND",
        trigger_type="PULLBACK_CONTINUATION",
        entry_price=4430.00,
        timestamp_utc=now_iso
    )
    registry.publish_signal(sig1)

    # 1. Candidate identical signal from another bot -> 100 points
    sig_identical = StrategyFingerprint(
        signal_id="SIG_TEST_2",
        bot_id="BOT_CLONE",
        symbol="XAUUSD",
        direction="BUY",                # +25
        strategy_name="EMA_PULLBACK",   # +10
        strategy_group="TREND",         # +20
        trigger_type="PULLBACK_CONTINUATION",
        entry_price=4430.20,            # within $1.50 -> +25
        timestamp_utc=now_iso           # within 300s -> +20
    )
    score, reason, _ = registry.calculate_duplicate_exposure_score(sig_identical)
    assert score == 100
    assert "HIGH_DUPLICATE_EXPOSURE" in reason

    # 2. Independent signal (different direction, different group, different price)
    sig_independent = StrategyFingerprint(
        signal_id="SIG_TEST_3",
        bot_id="BOT_2_REVERSAL",
        symbol="XAUUSD",
        direction="SELL",               # 0
        strategy_name="VWAP_MEAN_REVERSION", # 0
        strategy_group="MEAN_REVERSION",# 0
        trigger_type="EXTREME_REVERSAL",# 0
        entry_price=4445.00,            # 0
        timestamp_utc=now_iso           # +20
    )
    score_ind, reason_ind, _ = registry.calculate_duplicate_exposure_score(sig_independent)
    assert score_ind == 20  # only time overlap
    assert score_ind <= 30  # classified as independent


# ════════════════════════════════════════════════════════════════════════
#  3. UNIT TESTS: PORTFOLIO RISK COORDINATOR
# ════════════════════════════════════════════════════════════════════════

def test_portfolio_risk_coordinator_pruning(tmp_path):
    """Verify that portfolio coordinator approves independent setups and vetoes duplicate active exposure."""
    risk_coord = PortfolioRiskCoordinator(shared_dir=str(tmp_path))

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    # 1. First independent signal from Bot 1
    sig1 = StrategyFingerprint(
        signal_id="SIG_A1",
        bot_id="BOT_1_TREND",
        direction="BUY",
        strategy_name="EMA_PULLBACK",
        strategy_group="TREND",
        trigger_type="PULLBACK_CONTINUATION",
        entry_price=4430.00,
        timestamp_utc=now_iso
    )
    res1 = risk_coord.evaluate_execution_approval(sig1, requested_lots=0.01)
    assert res1.approved is True
    assert res1.action == "APPROVE"

    # Register open position for Bot 1
    risk_coord.register_open_position("BOT_1_TREND", 1001, "XAUUSD", "BUY", 0.01, "EMA_PULLBACK", 4430.00)

    # 2. Duplicate signal from Bot 2/3 at the exact same price zone
    sig_duplicate = StrategyFingerprint(
        signal_id="SIG_B1",
        bot_id="BOT_CLONE",
        direction="BUY",
        strategy_name="EMA_PULLBACK",
        strategy_group="TREND",
        trigger_type="PULLBACK_CONTINUATION",
        entry_price=4430.10,
        timestamp_utc=now_iso
    )
    res_dup = risk_coord.evaluate_execution_approval(sig_duplicate, requested_lots=0.01)
    assert res_dup.approved is False
    assert res_dup.action == "REJECT"
    assert "DUPLICATE_EXPOSURE" in res_dup.rejection_reason


# ════════════════════════════════════════════════════════════════════════
#  4. MARKET SIMULATION SCENARIO TESTS (Per PDF Specification)
# ════════════════════════════════════════════════════════════════════════

def test_simulation_scenario_1_strong_trend():
    """
    SCENARIO 1: Strong Trend (TRENDING_UP)
    Expected: Bot 1 active, Bot 2 mostly inactive / blocked, Bot 3 selectively active.
    """
    regime = "trending_up"
    assert BOT_1_TREND_PROFILE.get_regime_priority(regime) == "HIGH"
    assert BOT_2_REVERSAL_PROFILE.get_regime_priority(regime) == "BLOCKED"
    assert BOT_3_STRUCTURE_PROFILE.get_regime_priority(regime) in ("MEDIUM", "HIGH")


def test_simulation_scenario_2_range_market():
    """
    SCENARIO 2: Range (RANGING)
    Expected: Bot 2 active, Bot 1 inactive / blocked, Bot 3 selective.
    """
    regime = "ranging"
    assert BOT_2_REVERSAL_PROFILE.get_regime_priority(regime) == "HIGH"
    assert BOT_1_TREND_PROFILE.get_regime_priority(regime) == "BLOCKED"
    assert BOT_3_STRUCTURE_PROFILE.get_regime_priority(regime) in ("LOW", "BLOCKED")


def test_simulation_scenario_3_liquidity_sweep_reversal():
    """
    SCENARIO 3: Liquidity Sweep + Reversal (STRUCTURAL_TRANSITION)
    Expected: Bot 3 active (primary), Bot 2 may confirm independently, Bot 1 inactive.
    """
    regime = "structural_transition"
    assert BOT_3_STRUCTURE_PROFILE.get_regime_priority(regime) == "HIGH"
    assert BOT_2_REVERSAL_PROFILE.get_regime_priority(regime) == "MEDIUM"
    assert BOT_1_TREND_PROFILE.get_regime_priority(regime) in ("MEDIUM", "BLOCKED")


def test_simulation_scenario_4_high_volatility_breakout():
    """
    SCENARIO 4: High Volatility Breakout (BREAKOUT_EXPANSION)
    Expected: Bot 3 primary active, Bot 2 blocked, Bot 1 may participate on continuation.
    """
    regime = "breakout_expansion"
    assert BOT_3_STRUCTURE_PROFILE.get_regime_priority(regime) == "HIGH"
    assert BOT_2_REVERSAL_PROFILE.get_regime_priority(regime) == "BLOCKED"
    assert BOT_1_TREND_PROFILE.get_regime_priority(regime) == "MEDIUM"
