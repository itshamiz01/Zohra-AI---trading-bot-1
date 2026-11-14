"""
╔══════════════════════════════════════════════════════════════════════╗
║               ZOHRA — STRATEGY DIAGNOSTIC LOGGER                     ║
║         Structured Evaluation Observability for XAUUSD Engine        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import datetime as dt
from typing import Dict, Tuple, Optional
from zohra.core.market_regime import RegimeReport
from zohra.core.signal_arbitrator import ArbitrationResult

logger = logging.getLogger("zohra.strategy_diagnostics")


def log_strategy_evaluation(
    timeframe: str,
    regime_report: RegimeReport,
    eligibility: Dict[str, Tuple[bool, str]],
    arbitration_res: ArbitrationResult
) -> str:
    """
    Renders and logs the comprehensive evaluation cycle banner.
    """
    now_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Format Strategy Eligibility lines
    def fmt_el(strat_key: str) -> str:
        if strat_key in eligibility:
            is_ok, reason = eligibility[strat_key]
            status = "ELIGIBLE" if is_ok else "NOT ELIGIBLE"
            return f"{status:<12} | {reason}"
        return "UNKNOWN"

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "                XAUUSD STRATEGY EVALUATION                  ",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"TIMESTAMP:           {now_str}",
        f"TIMEFRAME:           {timeframe}",
        f"MARKET REGIME:       {regime_report.regime.value} (Confidence: {regime_report.confidence}%)",
        f"REGIME EXPLANATION:  {regime_report.explanation}",
        "────────────────────────────────────────────────────────────",
        f"EMA_PULLBACK:        {fmt_el('EMA_PULLBACK_TREND')}",
        f"VWAP_MEAN_REVERSION: {fmt_el('VWAP_MEAN_REVERSION')}",
        f"LIQUIDITY_MSS:       {fmt_el('LIQUIDITY_SWEEP_MSS')}",
        f"BREAKOUT:            {fmt_el('BREAKOUT_EXPANSION')}",
        f"BOLLINGER_RSI:       {fmt_el('BOLLINGER_RSI_REVERSAL')}",
        "────────────────────────────────────────────────────────────",
    ]

    if arbitration_res.decision == "TRADE" and arbitration_res.signal:
        sig = arbitration_res.signal
        support_str = f" | Supporting: {', '.join(arbitration_res.supporting_strategies)}" if arbitration_res.supporting_strategies else ""
        lines.extend([
            f"PRIMARY STRATEGY:    {arbitration_res.primary_strategy}{support_str}",
            f"SIGNAL DETAILS:      {sig.direction} XAUUSD @ {sig.entry_price:.2f} | SL={sig.stop_loss:.2f} | TP={sig.take_profit:.2f} (R:R={sig.risk_reward})",
            f"SCORE & GRADE:       Score={arbitration_res.final_score}/100 [Grade {arbitration_res.grade}]",
            f"FINAL DECISION:      🟢 TRADE APPROVED"
        ])
    else:
        lines.extend([
            f"FINAL DECISION:      🔴 NO_TRADE",
            f"FINAL REASON:        {arbitration_res.rejection_reason or 'No qualified candidate met score threshold'}"
        ])

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    banner_text = "\n".join(lines)
    logger.info(banner_text)
    return banner_text
