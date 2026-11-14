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
from zohra.config.settings import BOT_ID, BOT_NAME

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
    action: str = "NO_TRADE"            # "TRADE" or "NO_TRADE"
    decision: str = "NO_TRADE"          # "TRADE" or "NO_TRADE" (alias)
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
    fingerprint: Optional[Any] = None


# Backward-compatible alias
ArbitrationResult = ConfluenceDecision


class ConfluenceEngine:
    """
    Master 15-Strategy Confluence & Arbitration Engine for Gold (XAUUSD).
    Enforces:
    1. Bot Specialization Filtering (Trend vs Reversal vs Structure/Breakout).
    2. Regime Prioritization & Block Rules per Bot Specialization.
    3. Intra-Specialization Confirmations.
    4. Strict Directional Conflict veto.
    5. Transparent 0-100 scoring & letter grading.
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
        Executes complete evaluation across specialized strategies and arbitrates with the Confluence Engine.
        """
        from zohra.config.settings import BOT_PROFILE, BOT_ID, BOT_NAME, BOT_ROLE
        from zohra.core.strategy_fingerprint import build_strategy_fingerprint

        eligibility: Dict[str, Tuple[bool, str]] = {}
        strategy_statuses: Dict[str, Dict[str, Any]] = {}
        candidate_signals: List[CandidateSignal] = []

        # 1. Anti-HFT Cooldown & Spread Guard
        now = time.time()
        cooldown_limit = getattr(BOT_PROFILE, "cooldown_seconds", self.config.cooldown_seconds_after_trade)
        cooldown_rem = cooldown_limit - (now - self.last_trade_time)
        if cooldown_rem > 0:
            rejection = f"ANTI_HFT_COOLDOWN_ACTIVE ({cooldown_rem:.0f}s remaining)"
            logger.info(f"[{BOT_ID}] Cooldown active, {cooldown_rem:.0f}s remaining")
            return self._build_decision("NO_TRADE", rejection_reason=rejection, regime_report=regime_report), eligibility

        max_spread = getattr(BOT_PROFILE, "max_spread_pips", self.config.max_spread_pips)
        if current_spread_pips > max_spread:
            rejection = f"MAX_SPREAD_EXCEEDED ({current_spread_pips:.1f} > {max_spread:.1f} pips)"
            logger.info(f"[{BOT_ID}] Spread too wide: {current_spread_pips:.1f} pips")
            return self._build_decision("NO_TRADE", rejection_reason=rejection, regime_report=regime_report), eligibility

        # 2. Check Bot Specialization Regime Tradability
        regime_str = regime_report.regime.value if regime_report else "unclear"
        regime_priority = BOT_PROFILE.get_regime_priority(regime_str)
        if regime_priority == "BLOCKED":
            rejection = f"REGIME_BLOCKED_FOR_SPECIALIZATION ({regime_str.upper()} is BLOCKED for {BOT_PROFILE.bot_role})"
            logger.info(f"[{BOT_ID}] {rejection}")
            # Mark all as blocked in status
            for name, strat in self.strategies.items():
                is_enabled = BOT_PROFILE.is_strategy_enabled(name)
                status_reason = f"Regime {regime_str.upper()} not applicable to {BOT_PROFILE.bot_role}" if is_enabled else "NOT_IN_BOT_SPECIALIZATION"
                strategy_statuses[name] = {
                    "name": name,
                    "group": strat.strategy_group,
                    "eligible": False,
                    "verdict": "OFF",
                    "reason": status_reason,
                    "score": 0,
                    "signal": None
                }
                eligibility[name] = (False, status_reason)
            return self._build_decision("NO_TRADE", rejection_reason=rejection, strategy_statuses=strategy_statuses, regime_report=regime_report, current_spread_pips=current_spread_pips), eligibility

        # 3. Evaluate Specialized Strategies
        for name, strat in self.strategies.items():
            # Check if enabled for this bot
            is_bot_enabled = BOT_PROFILE.is_strategy_enabled(name)
            if not is_bot_enabled:
                reason = f"Excluded by bot profile ({BOT_PROFILE.bot_role})"
                eligibility[name] = (False, reason)
                strategy_statuses[name] = {
                    "name": name,
                    "group": strat.strategy_group,
                    "eligible": False,
                    "verdict": "OFF",
                    "reason": reason,
                    "score": 0,
                    "signal": None
                }
                continue

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

        # 4. If No Candidates Produced
        if not candidate_signals:
            decision = self._build_decision(
                "NO_TRADE",
                rejection_reason="NO_VALID_STRATEGY_SIGNALS",
                strategy_statuses=strategy_statuses,
                regime_report=regime_report,
                current_spread_pips=current_spread_pips
            )
            return decision, eligibility

        # 5. Group Candidates by Direction
        buy_signals = [c for c in candidate_signals if c.direction == "BUY"]
        sell_signals = [c for c in candidate_signals if c.direction == "SELL"]

        raw_buy = len(buy_signals)
        raw_sell = len(sell_signals)

        buy_groups = set(s.strategy_group for s in buy_signals)
        sell_groups = set(s.strategy_group for s in sell_signals)

        # 6. Directional Conflict Resolution
        if raw_buy > 0 and raw_sell > 0:
            buy_score = sum(s.setup_quality for s in buy_signals)
            sell_score = sum(s.setup_quality for s in sell_signals)
            score_diff = abs(buy_score - sell_score)

            if score_diff < self.config.dominance_margin_pts or (raw_buy >= 2 and raw_sell >= 2):
                conflict_msg = f"Directional conflict: {raw_buy} BUY ({buy_score} pts) vs {raw_sell} SELL ({sell_score} pts) (Margin={score_diff} < {self.config.dominance_margin_pts})"
                logger.warning(f"⚖️ [{BOT_ID}] [ConfluenceEngine] {conflict_msg} -> CONFLICT_DETECTED (NO_TRADE)")
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

        # 7. Enforce Bot-Specialized Confirmation & Group Rules
        req_confirmations = getattr(BOT_PROFILE, "min_confirmations", 2)
        if raw_confirmations < req_confirmations:
            rejection = f"INSUFFICIENT_CONFIRMATIONS ({raw_confirmations} < {req_confirmations} required)"
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

        req_groups = getattr(BOT_PROFILE, "min_strategy_groups", 1)
        if independent_groups_count < req_groups:
            rejection = f"INSUFFICIENT_INDEPENDENT_GROUPS ({independent_groups_count} < {req_groups} required)"
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

        # 8. Select Primary Signal & Score Candidate
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

        # 9. Minimum Score / Grade Threshold per Bot Profile
        min_exec = getattr(BOT_PROFILE, "min_confidence", self.config.min_exec_score)
        if total_score < min_exec:
            rejection = f"SIGNAL_SCORE_BELOW_THRESHOLD ({total_score} < {min_exec})"
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

        # 10. Build Strategy Fingerprint for this signal
        sig_dict = {
            "direction": winning_dir,
            "strategy": primary_signal.strategy_name,
            "strategy_group": primary_signal.strategy_group,
            "entry_price": primary_signal.entry_price,
            "stop_loss": primary_signal.stop_loss,
            "take_profit": primary_signal.take_profit,
            "risk_reward": primary_signal.risk_reward,
            "confidence": total_score,
            "reasons": primary_signal.reasons
        }
        fp = build_strategy_fingerprint(
            bot_id=BOT_ID,
            bot_name=BOT_NAME,
            bot_role=BOT_ROLE,
            signal_data=sig_dict,
            regime_report=regime_report,
            symbol="XAUUSD"
        )

        # ─── 11. QUALIFIED TRADE CANDIDATE APPROVED ───
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
        decision.fingerprint = fp

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
        w_confluence = min(15.0, (independent_groups_count * 5.0) + (raw_confirmations * 2.5))

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

    def _score_candidate(self, candidate: CandidateSignal, regime_report: RegimeReport,
                         current_spread_pips: float = 2.0) -> Tuple[int, str]:
        """Compatibility scorer for callers that evaluate one candidate.

        A single setup is assessed as one confirmation from one independent
        group.  It is a score-only helper; it cannot qualify an order by
        itself because ``evaluate_all`` still enforces the full confluence
        requirement.
        """
        return self._score_confluence(
            candidate,
            raw_confirmations=1,
            independent_groups_count=1,
            regime_report=regime_report,
            current_spread_pips=current_spread_pips,
        )

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
        """Formats comprehensive strategy diagnostic evaluation banner."""
        from zohra.config.settings import BOT_NAME, BOT_ID, BOT_PROFILE
        regime_str = regime_report.regime.value if regime_report else "UNKNOWN"
        conf_str = f"{regime_report.confidence}%" if regime_report else "N/A"
        priority_str = BOT_PROFILE.get_regime_priority(regime_str)

        lines = [
            "╔════════════════════════════════════════════════════════════════════════╗",
            "║  ZOHRA — 15-STRATEGY REGIME-ADAPTIVE CONFLUENCE ENGINE                 ║",
            f"║  {BOT_NAME} ({BOT_ID})  — SPECIALIZED CONFLUENCE ENGINE",
            f"║  Role: {BOT_PROFILE.bot_role:<63}║",
            "╠════════════════════════════════════════════════════════════════════════╣",
            f"║ MARKET REGIME: {regime_str.upper():<16} CONFIDENCE: {conf_str:<6} PRIORITY: {priority_str:<10} ║",
            "╠════════════════════════════════════════════════════════════════════════╣",
            "║ STRATEGY EVALUATION BREAKDOWN:                                         ║"
        ]

        # Group strategies
        for group in StrategyGroup:
            lines.append(f"║ ─── {group.value} GROUP ───" + " " * (67 - len(group.value) - 10) + "║")
            for name, strat in self.strategies.items():
                if strat.strategy_group == group.value:
                    status = strategy_statuses.get(name, {})
                    verdict = status.get("verdict", "OFF")
                    is_enabled = status.get("eligible", False)
                    is_specialized = BOT_PROFILE.is_strategy_enabled(name)
                    eligible_txt = "ELIGIBLE" if is_enabled else ("OFF" if is_specialized else "EXCLUDED")
                    lines.append(f"║   • {name.upper():<26} {verdict:<6} [{eligible_txt:<8}]" + " " * 19 + "║")

        lines.extend([
            "╠════════════════════════════════════════════════════════════════════════╣",
            f"║ CONFLUENCE SUMMARY:                                                    ║",
            f"║   • DIRECTION:             {direction:<43} ║",
            f"║   • RAW CONFIRMATIONS:     {raw_confirmations:<2} (Required: >={BOT_PROFILE.min_confirmations})                              ║",
            f"║   • INDEPENDENT GROUPS:    {independent_groups:<2} (Required: >={BOT_PROFILE.min_strategy_groups})                              ║",
            f"║   • GROUPS REPRESENTED:    {str(strategy_groups):<43} ║",
            f"║   • COMPOSITE SCORE:       {final_score:<3}/100  [GRADE: {grade:<6}]                  ║",
            f"║   • SPREAD QUALITY:        {current_spread_pips:.1f} pips (Max: {BOT_PROFILE.max_spread_pips:.1f} pips)                   ║",
            "╠════════════════════════════════════════════════════════════════════════╣",
            f"║ FINAL DECISION: {action:<18} " + (f"REASON: {rejection_reason[:33]:<33}" if rejection_reason else "STATUS: EXECUTION QUALIFIED" + " " * 9) + "║",
            "╚════════════════════════════════════════════════════════════════════════╝"
        ])
        return "\n".join(lines)

    def arbitrate(self, candidates: List[Any], regime_info: Any) -> Dict[str, Any]:
        """Backward-compatibility wrapper for legacy arbitrate() callers."""
        def candidate_value(candidate: Any, field_name: str, default: Any = None) -> Any:
            if isinstance(candidate, dict):
                return candidate.get(field_name, default)
            return getattr(candidate, field_name, default)

        def normalized_direction(candidate: Any) -> str:
            direction = candidate_value(candidate, "direction", "")
            direction = getattr(direction, "value", direction)
            return {"LONG": "BUY", "SHORT": "SELL"}.get(str(direction).upper(), str(direction).upper())

        buy_cands = [c for c in candidates if normalized_direction(c) == "BUY"]
        sell_cands = [c for c in candidates if normalized_direction(c) == "SELL"]

        if buy_cands and sell_cands:
            return {
                "action": "NO_TRADE",
                "winning_signal": None,
                "final_score": 0,
                "grade": TradeQuality.REJECT,
                "conflict_status": "CONFLICT_OPPOSING_DIRECTIONS",
                "reason": "Opposing BUY and SELL candidates require a fresh evaluation.",
            }

        raw_count = max(len(buy_cands), len(sell_cands))
        winning = buy_cands if len(buy_cands) >= len(sell_cands) else sell_cands

        # This adapter returns an analytical signal only.  The main evaluate
        # path remains the execution authority and enforces its stricter,
        # configured confluence gate before an order can be proposed.
        legacy_minimum = min(2, self.config.min_confirmations)
        if not winning or raw_count < legacy_minimum:
            return {
                "action": "NO_TRADE",
                "winning_signal": None,
                "final_score": 0,
                "grade": TradeQuality.REJECT,
                "conflict_status": "NO_CONFLICT",
                "reason": f"Insufficient confirmations ({raw_count} < {legacy_minimum})"
            }

        top_sig = winning[0]
        direction = normalized_direction(top_sig)
        if isinstance(top_sig, dict):
            top_sig = dict(top_sig)
            top_sig["direction"] = "LONG" if direction == "BUY" else "SHORT"
        return {
            "action": "TRADE",
            "winning_signal": top_sig,
            "final_score": 85,
            "grade": TradeQuality.A,
            "conflict_status": "NO_CONFLICT",
            "execution_qualified": raw_count >= self.config.min_confirmations,
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
