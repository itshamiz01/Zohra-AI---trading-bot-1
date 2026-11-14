"""
╔══════════════════════════════════════════════════════════════════════╗
║        ZOHRA — 15-STRATEGY CONFLUENCE & ARBITRATION ENGINE           ║
║       3-Confirmation Rule, Group Independence & Conflict Veto        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
import pandas as pd

from zohra.core.market_regime import MarketRegime, RegimeReport, market_regime_engine
from zohra.core.enums import StrategyGroup, StrategyName, TradeQuality
from zohra.strategies.base_strategy import CandidateSignal, BaseStrategy
from zohra.config.strategy_config import strategy_config

# Import all 15 Scalping Strategies
from zohra.strategies.ema_pullback import EmaPullbackStrategy
from zohra.strategies.vwap_mean_reversion import VwapMeanReversionStrategy
from zohra.strategies.liquidity_mss import LiquidityMssStrategy
from zohra.strategies.breakout import BreakoutStrategy
from zohra.strategies.bollinger_rsi import BollingerRsiStrategy
from zohra.strategies.fibonacci_pullback import FibonacciPullbackStrategy
from zohra.strategies.support_resistance import SupportResistanceStrategy
from zohra.strategies.supply_demand import SupplyDemandStrategy
from zohra.strategies.fvg import FvgRetracementStrategy
from zohra.strategies.order_block import OrderBlockStrategy
from zohra.strategies.volume_breakout import VolumeBreakoutStrategy
from zohra.strategies.atr_expansion import AtrExpansionStrategy
from zohra.strategies.momentum_continuation import MomentumContinuationStrategy
from zohra.strategies.mtf_alignment import MtfAlignmentStrategy
from zohra.strategies.false_breakout import FalseBreakoutStrategy

logger = logging.getLogger("zohra.core.confluence_engine")


@dataclass
class ConfluenceDecision:
    """Final decision produced by the 15-Strategy Confluence Engine."""
    action: str                         # "TRADE" or "NO_TRADE"
    decision: str                       # "TRADE" or "NO_TRADE" (alias)
    winning_signal: Optional[CandidateSignal] = None
    signal: Optional[CandidateSignal] = None  # alias
    final_score: int = 0                # 0 to 100
    grade: str = "REJECT"               # A+, A, B, C, REJECT
    direction: str = "NONE"             # "BUY", "SELL", "NONE"
    primary_strategy: str = "NONE"
    supporting_strategies: List[str] = field(default_factory=list)
    raw_confirmations: int = 0
    independent_groups: int = 0
    strategy_groups: List[str] = field(default_factory=list)
    conflict_detected: bool = False
    rejection_reason: str = ""
    strategy_statuses: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    diagnostic_box: str = ""


# Backward-compatible alias
ArbitrationResult = ConfluenceDecision


class ConfluenceEngine:
    """
    Master 15-Strategy Confluence & Arbitration Engine for Gold (XAUUSD).
    Enforces:
    1. Minimum 3 valid confirmations in the identical direction.
    2. Minimum 2 independent Strategy Groups represented (Mode A) or 3 groups (Mode B).
    3. Strict Directional Conflict veto (opposing signals or low dominance margin -> NO_TRADE).
    4. Transparent 0-100 scoring & letter grading.
    """

    def __init__(self, config=None):
        self.config = config or strategy_config.confluence
        self.strategies: Dict[str, BaseStrategy] = {
            # ─── Group 1: Trend ───
            StrategyName.EMA_PULLBACK.value: EmaPullbackStrategy(),
            StrategyName.FIBONACCI_PULLBACK.value: FibonacciPullbackStrategy(),
            StrategyName.MTF_ALIGNMENT.value: MtfAlignmentStrategy(),
            StrategyName.MOMENTUM_CONTINUATION.value: MomentumContinuationStrategy(),
            # ─── Group 2: Mean Reversion ───
            StrategyName.VWAP_MEAN_REVERSION.value: VwapMeanReversionStrategy(),
            StrategyName.BOLLINGER_RSI.value: BollingerRsiStrategy(),
            StrategyName.SR_REJECTION.value: SupportResistanceStrategy(),
            # ─── Group 3: Structure / SMC ───
            StrategyName.LIQUIDITY_MSS.value: LiquidityMssStrategy(),
            StrategyName.SUPPLY_DEMAND.value: SupplyDemandStrategy(),
            StrategyName.FVG_RETRACEMENT.value: FvgRetracementStrategy(),
            StrategyName.ORDER_BLOCK.value: OrderBlockStrategy(),
            StrategyName.FALSE_BREAKOUT.value: FalseBreakoutStrategy(),
            # ─── Group 4: Breakout / Volatility ───
            StrategyName.BREAKOUT.value: BreakoutStrategy(),
            StrategyName.VOLUME_BREAKOUT.value: VolumeBreakoutStrategy(),
            StrategyName.ATR_EXPANSION.value: AtrExpansionStrategy()
        }
        self.last_trade_time: float = 0.0
        self.daily_trade_count: int = 0
        self.session_trade_count: int = 0

    def evaluate_all(self, df_entry: pd.DataFrame, df_htf: Optional[pd.DataFrame],
                     regime_report: RegimeReport, current_spread_pips: float = 2.0) -> Tuple[ConfluenceDecision, Dict[str, Tuple[bool, str]]]:
        """
        Executes complete evaluation across all 15 strategies and arbitrates with the Confluence Engine.
        """
        eligibility: Dict[str, Tuple[bool, str]] = {}
        strategy_statuses: Dict[str, Dict[str, Any]] = {}
        candidate_signals: List[CandidateSignal] = []

        # 1. Anti-HFT Cooldown & Spread Guard
        now = time.time()
        cooldown_rem = self.config.cooldown_seconds_after_trade - (now - self.last_trade_time)
        if cooldown_rem > 0:
            rejection = f"ANTI_HFT_COOLDOWN_ACTIVE ({cooldown_rem:.0f}s remaining)"
            return self._build_decision("NO_TRADE", rejection_reason=rejection), eligibility

        if current_spread_pips > self.config.max_spread_pips:
            rejection = f"MAX_SPREAD_EXCEEDED ({current_spread_pips:.1f} > {self.config.max_spread_pips:.1f} pips)"
            return self._build_decision("NO_TRADE", rejection_reason=rejection), eligibility

        # 2. Evaluate all 15 Strategies
        for name, strat in self.strategies.items():
            is_ok, reason = strat.is_eligible(regime_report)
            eligibility[name] = (is_ok, reason)

            status_entry = {
                "name": name,
                "group": strat.strategy_group,
                "eligible": is_ok,
                "verdict": "OFF" if not is_ok else "NONE",
                "reason": reason,
                "score": 0,
                "signal": None
            }

            if is_ok:
                try:
                    sig = strat.evaluate(df_entry, df_htf, regime_report, current_spread_pips)
                    if sig is not None and sig.is_valid:
                        candidate_signals.append(sig)
                        status_entry["verdict"] = sig.direction
                        status_entry["reason"] = "; ".join(sig.reasons)
                        status_entry["score"] = sig.setup_quality
                        status_entry["signal"] = sig
                except Exception as e:
                    logger.error(f"Error evaluating {name}: {e}")
                    status_entry["reason"] = f"Evaluation error: {e}"

            strategy_statuses[name] = status_entry

        # 3. If No Candidates Produced
        if not candidate_signals:
            decision = self._build_decision(
                "NO_TRADE",
                rejection_reason="NO_VALID_STRATEGY_SIGNALS",
                strategy_statuses=strategy_statuses,
                regime_report=regime_report,
                current_spread_pips=current_spread_pips
            )
            return decision, eligibility

        # 4. Group Candidates by Direction
        buy_signals = [c for c in candidate_signals if c.direction == "BUY"]
        sell_signals = [c for c in candidate_signals if c.direction == "SELL"]

        raw_buy = len(buy_signals)
        raw_sell = len(sell_signals)

        buy_groups = set(s.strategy_group for s in buy_signals)
        sell_groups = set(s.strategy_group for s in sell_signals)

        # 5. Directional Conflict Resolution
        if raw_buy > 0 and raw_sell > 0:
            buy_score = sum(s.setup_quality for s in buy_signals)
            sell_score = sum(s.setup_quality for s in sell_signals)
            score_diff = abs(buy_score - sell_score)

            if score_diff < self.config.dominance_margin_pts or (raw_buy >= 2 and raw_sell >= 2):
                conflict_msg = f"Directional conflict: {raw_buy} BUY ({buy_score} pts) vs {raw_sell} SELL ({sell_score} pts) (Margin={score_diff} < {self.config.dominance_margin_pts})"
                logger.warning(f"⚖️ [ConfluenceEngine] {conflict_msg} -> CONFLICT_DETECTED (NO_TRADE)")
                decision = self._build_decision(
                    "NO_TRADE",
                    conflict_detected=True,
                    rejection_reason=f"CONFLICT_DETECTED: {conflict_msg}",
                    strategy_statuses=strategy_statuses,
                    regime_report=regime_report,
                    current_spread_pips=current_spread_pips
                )
                return decision, eligibility

            # Winner based on dominance
            winning_signals = buy_signals if buy_score > sell_score else sell_signals
            winning_dir = "BUY" if buy_score > sell_score else "SELL"
            winning_groups = buy_groups if buy_score > sell_score else sell_groups
        elif raw_buy > 0:
            winning_signals = buy_signals
            winning_dir = "BUY"
            winning_groups = buy_groups
        else:
            winning_signals = sell_signals
            winning_dir = "SELL"
            winning_groups = sell_groups

        raw_confirmations = len(winning_signals)
        independent_groups_count = len(winning_groups)

        # 6. Enforce Three-Confirmation & Group Independence Rules
        if raw_confirmations < self.config.min_confirmations:
            rejection = f"INSUFFICIENT_CONFIRMATIONS ({raw_confirmations} < {self.config.min_confirmations} required)"
            decision = self._build_decision(
                "NO_TRADE",
                direction=winning_dir,
                raw_confirmations=raw_confirmations,
                independent_groups=independent_groups_count,
                strategy_groups=list(winning_groups),
                rejection_reason=rejection,
                strategy_statuses=strategy_statuses,
                regime_report=regime_report,
                current_spread_pips=current_spread_pips
            )
            return decision, eligibility

        min_req_groups = 3 if self.config.confluence_mode == "MODE_B" else self.config.min_strategy_groups
        if independent_groups_count < min_req_groups:
            rejection = f"INSUFFICIENT_INDEPENDENT_GROUPS ({independent_groups_count} < {min_req_groups} required; all belong to {list(winning_groups)})"
            decision = self._build_decision(
                "NO_TRADE",
                direction=winning_dir,
                raw_confirmations=raw_confirmations,
                independent_groups=independent_groups_count,
                strategy_groups=list(winning_groups),
                rejection_reason=rejection,
                strategy_statuses=strategy_statuses,
                regime_report=regime_report,
                current_spread_pips=current_spread_pips
            )
            return decision, eligibility

        # 7. Select Primary Signal & Score Candidate
        winning_signals.sort(key=lambda s: s.setup_quality, reverse=True)
        primary_signal = winning_signals[0]
        supporting_strats = [s.strategy_name for s in winning_signals[1:]]

        total_score, grade = self._score_confluence(
            primary_signal=primary_signal,
            raw_confirmations=raw_confirmations,
            independent_groups_count=independent_groups_count,
            regime_report=regime_report,
            current_spread_pips=current_spread_pips
        )

        # 8. Minimum Score / Grade Threshold
        if total_score < self.config.min_exec_score:
            rejection = f"SIGNAL_SCORE_BELOW_THRESHOLD ({total_score} < {self.config.min_exec_score})"
            decision = self._build_decision(
                "NO_TRADE",
                winning_signal=primary_signal,
                final_score=total_score,
                grade=grade,
                direction=winning_dir,
                primary_strategy=primary_signal.strategy_name,
                supporting_strategies=supporting_strats,
                raw_confirmations=raw_confirmations,
                independent_groups=independent_groups_count,
                strategy_groups=list(winning_groups),
                rejection_reason=rejection,
                strategy_statuses=strategy_statuses,
                regime_report=regime_report,
                current_spread_pips=current_spread_pips
            )
            return decision, eligibility

        # ─── 9. QUALIFIED TRADE CANDIDATE APPROVED ───
        decision = self._build_decision(
            "TRADE",
            winning_signal=primary_signal,
            final_score=total_score,
            grade=grade,
            direction=winning_dir,
            primary_strategy=primary_signal.strategy_name,
            supporting_strategies=supporting_strats,
            raw_confirmations=raw_confirmations,
            independent_groups=independent_groups_count,
            strategy_groups=list(winning_groups),
            rejection_reason="",
            strategy_statuses=strategy_statuses,
            regime_report=regime_report,
            current_spread_pips=current_spread_pips
        )
        return decision, eligibility

    def _score_confluence(self, primary_signal: CandidateSignal, raw_confirmations: int,
                          independent_groups_count: int, regime_report: RegimeReport,
                          current_spread_pips: float) -> Tuple[int, str]:
        """Calculates transparent 0-100 composite score & letter grade."""
        # 1. Regime Match (20 pts)
        w_regime = (primary_signal.regime_match_score / 100.0) * 20.0

        # 2. Setup Quality (20 pts)
        w_quality = (primary_signal.setup_quality / 100.0) * 20.0

        # 3. Group Diversity & Confluence Boost (15 pts)
        w_confluence = min(15.0, (independent_groups_count * 4.0) + (raw_confirmations * 1.5))

        # 4. Trend / Structure Alignment (15 pts)
        is_aligned = (
            (primary_signal.direction == "BUY" and regime_report.ema_alignment == "BULLISH") or
            (primary_signal.direction == "SELL" and regime_report.ema_alignment == "BEARISH") or
            (regime_report.regime in (MarketRegime.RANGING, MarketRegime.ROTATIONAL))
        )
        w_trend = 15.0 if is_aligned else 8.0

        # 5. Momentum & ADX (10 pts)
        w_momentum = 10.0 if regime_report.adx_value >= 20.0 else 6.0

        # 6. Volatility Quality (10 pts)
        w_vol = (primary_signal.volatility_score / 100.0) * 10.0

        # 7. Risk/Reward (5 pts)
        w_rr = 5.0 if primary_signal.risk_reward >= 2.0 else 3.5

        # 8. Spread Quality (5 pts)
        w_spread = 5.0 if current_spread_pips <= 2.0 else (3.0 if current_spread_pips <= 3.5 else 1.0)

        total_score = int(round(w_regime + w_quality + w_confluence + w_trend + w_momentum + w_vol + w_rr + w_spread))
        total_score = max(0, min(100, total_score))

        if total_score >= self.config.grade_a_plus_min:
            grade = "A+"
        elif total_score >= self.config.grade_a_min:
            grade = "A"
        elif total_score >= self.config.grade_b_min:
            grade = "B"
        elif total_score >= self.config.grade_c_min:
            grade = "C"
        else:
            grade = "REJECT"

        return total_score, grade

    def _build_decision(self, action: str, winning_signal: Optional[CandidateSignal] = None,
                        final_score: int = 0, grade: str = "REJECT", direction: str = "NONE",
                        primary_strategy: str = "NONE", supporting_strategies: List[str] = None,
                        raw_confirmations: int = 0, independent_groups: int = 0,
                        strategy_groups: List[str] = None, conflict_detected: bool = False,
                        rejection_reason: str = "", strategy_statuses: Dict[str, Any] = None,
                        regime_report: Optional[RegimeReport] = None, current_spread_pips: float = 2.0) -> ConfluenceDecision:
        supporting_strategies = supporting_strategies or []
        strategy_groups = strategy_groups or []
        strategy_statuses = strategy_statuses or {}

        diag_box = self.format_diagnostic_box(
            regime_report=regime_report,
            strategy_statuses=strategy_statuses,
            action=action,
            direction=direction,
            raw_confirmations=raw_confirmations,
            independent_groups=independent_groups,
            strategy_groups=strategy_groups,
            final_score=final_score,
            grade=grade,
            rejection_reason=rejection_reason,
            current_spread_pips=current_spread_pips
        )

        return ConfluenceDecision(
            action=action,
            decision=action,
            winning_signal=winning_signal,
            signal=winning_signal,
            final_score=final_score,
            grade=grade,
            direction=direction,
            primary_strategy=primary_strategy,
            supporting_strategies=supporting_strategies,
            raw_confirmations=raw_confirmations,
            independent_groups=independent_groups,
            strategy_groups=strategy_groups,
            conflict_detected=conflict_detected,
            rejection_reason=rejection_reason,
            strategy_statuses=strategy_statuses,
            diagnostic_box=diag_box
        )

    def format_diagnostic_box(self, regime_report: Optional[RegimeReport],
                              strategy_statuses: Dict[str, Any], action: str,
                              direction: str, raw_confirmations: int,
                              independent_groups: int, strategy_groups: List[str],
                              final_score: int, grade: str, rejection_reason: str,
                              current_spread_pips: float = 2.0) -> str:
        """Formats comprehensive 15-strategy diagnostic evaluation banner."""
        regime_str = regime_report.regime.value if regime_report else "UNKNOWN"
        conf_str = f"{regime_report.confidence}%" if regime_report else "N/A"

        lines = [
            "╔════════════════════════════════════════════════════════════════════════╗",
            "║        ZOHRA — 15-STRATEGY REGIME-ADAPTIVE CONFLUENCE ENGINE           ║",
            "║                  Institutional Gold (XAUUSD) Scalper                   ║",
            "╠════════════════════════════════════════════════════════════════════════╣",
            f"║ MARKET REGIME: {regime_str.upper():<25} CONFIDENCE: {conf_str:<18} ║",
            "╠════════════════════════════════════════════════════════════════════════╣",
            "║ 15-STRATEGY EVALUATION BREAKDOWN:                                     ║"
        ]

        # Group strategies
        for group in StrategyGroup:
            lines.append(f"║ ─── {group.value} GROUP ───" + " " * (67 - len(group.value) - 10) + "║")
            for name, strat in self.strategies.items():
                if strat.strategy_group == group.value:
                    status = strategy_statuses.get(name, {})
                    verdict = status.get("verdict", "OFF")
                    eligible_txt = "ELIGIBLE" if status.get("eligible", False) else "OFF"
                    lines.append(f"║   • {name.upper():<26} {verdict:<6} [{eligible_txt:<8}]" + " " * 19 + "║")

        lines.extend([
            "╠════════════════════════════════════════════════════════════════════════╣",
            f"║ CONFLUENCE SUMMARY:                                                    ║",
            f"║   • DIRECTION:             {direction:<43} ║",
            f"║   • RAW CONFIRMATIONS:     {raw_confirmations:<2} (Required: >={self.config.min_confirmations})                              ║",
            f"║   • INDEPENDENT GROUPS:    {independent_groups:<2} (Required: >={self.config.min_strategy_groups} - Mode A)                    ║",
            f"║   • GROUPS REPRESENTED:    {str(strategy_groups):<43} ║",
            f"║   • COMPOSITE SCORE:       {final_score:<3}/100  [GRADE: {grade:<6}]                  ║",
            f"║   • SPREAD QUALITY:        {current_spread_pips:.1f} pips (Max: {self.config.max_spread_pips:.1f} pips)                   ║",
            "╠════════════════════════════════════════════════════════════════════════╣",
            f"║ FINAL DECISION: {action:<18} " + (f"REASON: {rejection_reason[:33]:<33}" if rejection_reason else "STATUS: EXECUTION QUALIFIED" + " " * 9) + "║",
            "╚════════════════════════════════════════════════════════════════════════╝"
        ])
        return "\n".join(lines)

    def arbitrate(self, candidates: List[Any], regime_info: Any) -> Dict[str, Any]:
        """Backward-compatibility wrapper for legacy arbitrate() callers."""
        buy_cands = [c for c in candidates if getattr(c, "direction", c.get("direction")) == "BUY"]
        sell_cands = [c for c in candidates if getattr(c, "direction", c.get("direction")) == "SELL"]
        raw_count = max(len(buy_cands), len(sell_cands))
        winning = buy_cands if len(buy_cands) >= len(sell_cands) else sell_cands

        if not winning or raw_count < self.config.min_confirmations:
            return {
                "action": "NO_TRADE",
                "winning_signal": None,
                "final_score": 0,
                "grade": TradeQuality.REJECT,
                "reason": f"Insufficient confirmations ({raw_count} < {self.config.min_confirmations})"
            }

        top_sig = winning[0]
        return {
            "action": "TRADE",
            "winning_signal": top_sig,
            "final_score": 85,
            "grade": TradeQuality.A,
            "reason": f"{raw_count} valid confirmations qualified"
        }

    def record_execution(self):
        """Updates anti-HFT timers after an order is executed."""
        self.last_trade_time = time.time()
        self.daily_trade_count += 1
        self.session_trade_count += 1


# Master singleton instance
confluence_engine = ConfluenceEngine()
signal_arbitrator = confluence_engine
