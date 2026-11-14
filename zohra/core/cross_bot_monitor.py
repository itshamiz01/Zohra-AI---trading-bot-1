"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — CROSS-BOT CORRELATION MONITOR                      ║
║    Detects correlated signals across multiple bot instances           ║
║    DIAGNOSTIC ONLY — Does NOT block or modify trade execution        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import logging
import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger("zohra.cross_bot_monitor")


@dataclass
class SignalSnapshot:
    """Captures a single bot's signal decision for cross-bot comparison."""
    bot_id: str = ""
    bot_name: str = ""
    timestamp_utc: str = ""
    symbol: str = ""
    timeframe: str = "M5"
    candle_time: str = ""
    market_regime: str = ""
    regime_confidence: int = 0
    direction: str = "NONE"
    action: str = "NO_TRADE"
    raw_confirmations: int = 0
    independent_groups: int = 0
    strategy_groups: List[str] = field(default_factory=list)
    composite_score: int = 0
    grade: str = "REJECT"
    primary_strategy: str = "NONE"
    supporting_strategies: List[str] = field(default_factory=list)
    rejection_reason: str = ""
    # Per-strategy breakdown
    strategy_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class CrossBotMonitor:
    """
    Logs each bot's signal decisions to a shared directory for cross-bot
    correlation analysis.

    IMPORTANT: This module is DIAGNOSTIC ONLY. It does NOT block, modify,
    or interfere with trade execution in any way.
    """

    def __init__(self):
        from zohra.config.settings import BOT_ID, BOT_NAME
        self.bot_id = BOT_ID
        self.bot_name = BOT_NAME

        # Shared log directory — all bots write here for cross-comparison
        self.shared_log_dir = os.getenv(
            "CROSS_BOT_LOG_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "logs", "cross_bot")
        )
        os.makedirs(self.shared_log_dir, exist_ok=True)

        # Per-bot signal log file
        bot_suffix = self.bot_id.split("_")[-1].lower()
        self.signal_log_path = os.path.join(
            self.shared_log_dir, f"signals_{bot_suffix}.jsonl"
        )

        logger.info(
            f"📡 CrossBotMonitor initialized for {self.bot_name} ({self.bot_id}). "
            f"Shared log dir: {self.shared_log_dir}"
        )

    def record_signal(self, confluence_decision, regime_report=None,
                      symbol: str = "XAUUSD", candle_time: str = "") -> SignalSnapshot:
        """
        Records a signal decision snapshot for cross-bot comparison.
        Called after each ConfluenceEngine evaluation.
        """
        now_utc = dt.datetime.now(dt.timezone.utc)

        snapshot = SignalSnapshot(
            bot_id=self.bot_id,
            bot_name=self.bot_name,
            timestamp_utc=now_utc.isoformat(),
            symbol=symbol,
            candle_time=candle_time,
            market_regime=regime_report.regime.value if regime_report else "UNKNOWN",
            regime_confidence=regime_report.confidence if regime_report else 0,
            direction=getattr(confluence_decision, "direction", "NONE"),
            action=getattr(confluence_decision, "action", "NO_TRADE"),
            raw_confirmations=getattr(confluence_decision, "raw_confirmations", 0),
            independent_groups=getattr(confluence_decision, "independent_groups", 0),
            strategy_groups=getattr(confluence_decision, "strategy_groups", []),
            composite_score=getattr(confluence_decision, "final_score", 0),
            grade=getattr(confluence_decision, "grade", "REJECT"),
            primary_strategy=getattr(confluence_decision, "primary_strategy", "NONE"),
            supporting_strategies=getattr(confluence_decision, "supporting_strategies", []),
            rejection_reason=getattr(confluence_decision, "rejection_reason", ""),
        )

        # Extract per-strategy details if available
        strategy_statuses = getattr(confluence_decision, "strategy_statuses", {})
        for strat_name, strat_status in strategy_statuses.items():
            snapshot.strategy_details[strat_name] = {
                "eligible": strat_status.get("eligible", False),
                "verdict": strat_status.get("verdict", "OFF"),
                "score": strat_status.get("score", 0),
                "reason": strat_status.get("reason", ""),
            }

        # Write to shared log
        try:
            with open(self.signal_log_path, "a", encoding="utf-8") as f:
                f.write(snapshot.to_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write cross-bot signal log: {e}")

        # Check for correlation with other bots (read their logs)
        if snapshot.action == "TRADE":
            self._check_cross_bot_correlation(snapshot)

        return snapshot

    def _check_cross_bot_correlation(self, current_snapshot: SignalSnapshot):
        """
        Checks if other bots have recently generated similar signals.
        Logs a WARNING if correlated signals are detected.
        DIAGNOSTIC ONLY — does NOT block trades.
        """
        correlation_window_seconds = 60  # Look back 60 seconds
        now = dt.datetime.now(dt.timezone.utc)
        cutoff = now - dt.timedelta(seconds=correlation_window_seconds)

        correlated_bots = []

        try:
            for log_file in Path(self.shared_log_dir).glob("signals_*.jsonl"):
                # Skip our own log
                if log_file.name == os.path.basename(self.signal_log_path):
                    continue

                # Read recent entries from other bot's log
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # Check last 10 entries (recent signals)
                    for line in lines[-10:]:
                        try:
                            entry = json.loads(line.strip())
                            entry_time = dt.datetime.fromisoformat(entry.get("timestamp_utc", ""))
                            if entry_time.tzinfo is None:
                                entry_time = entry_time.replace(tzinfo=dt.timezone.utc)

                            if entry_time >= cutoff:
                                if (entry.get("action") == "TRADE" and
                                        entry.get("direction") == current_snapshot.direction and
                                        entry.get("symbol") == current_snapshot.symbol):
                                    correlated_bots.append({
                                        "bot_id": entry.get("bot_id", "unknown"),
                                        "bot_name": entry.get("bot_name", "unknown"),
                                        "direction": entry.get("direction"),
                                        "primary_strategy": entry.get("primary_strategy"),
                                        "composite_score": entry.get("composite_score"),
                                        "candle_time": entry.get("candle_time"),
                                    })
                        except (json.JSONDecodeError, ValueError):
                            continue
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Error checking cross-bot correlation: {e}")
            return

        if correlated_bots:
            alert_msg = (
                f"\n{'='*70}\n"
                f"⚠️  CROSS-BOT CORRELATION ALERT (DIAGNOSTIC)\n"
                f"{'='*70}\n"
                f"Bot: {current_snapshot.bot_name} ({current_snapshot.bot_id})\n"
                f"Signal: {current_snapshot.direction} {current_snapshot.symbol}\n"
                f"Strategy: {current_snapshot.primary_strategy}\n"
                f"Score: {current_snapshot.composite_score}/100 [{current_snapshot.grade}]\n"
                f"\n"
                f"CORRELATED BOTS ({len(correlated_bots)} other bot(s) in same direction):\n"
            )
            for cb in correlated_bots:
                alert_msg += (
                    f"  → {cb['bot_name']} ({cb['bot_id']}): "
                    f"{cb['direction']} via {cb['primary_strategy']} "
                    f"(Score: {cb['composite_score']})\n"
                )
            alert_msg += (
                f"\n"
                f"RISK: Multiple bots responding to same market event.\n"
                f"Total correlated exposure: {len(correlated_bots) + 1}x position size.\n"
                f"{'='*70}\n"
            )

            logger.warning(alert_msg)

            # Write correlation alert to shared log
            try:
                alert_path = os.path.join(
                    self.shared_log_dir, "correlation_alerts.jsonl"
                )
                alert_entry = {
                    "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "triggering_bot": current_snapshot.bot_id,
                    "symbol": current_snapshot.symbol,
                    "direction": current_snapshot.direction,
                    "primary_strategy": current_snapshot.primary_strategy,
                    "correlated_bots": correlated_bots,
                    "total_exposure_multiplier": len(correlated_bots) + 1,
                }
                with open(alert_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(alert_entry, default=str) + "\n")
            except Exception as e:
                logger.error(f"Failed to write correlation alert: {e}")

    def get_recent_signals(self, lookback_minutes: int = 60) -> List[Dict]:
        """Returns recent signal snapshots from THIS bot."""
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=lookback_minutes)
        signals = []
        try:
            if os.path.exists(self.signal_log_path):
                with open(self.signal_log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            entry_time = dt.datetime.fromisoformat(entry.get("timestamp_utc", ""))
                            if entry_time.tzinfo is None:
                                entry_time = entry_time.replace(tzinfo=dt.timezone.utc)
                            if entry_time >= cutoff:
                                signals.append(entry)
                        except (json.JSONDecodeError, ValueError):
                            continue
        except Exception as e:
            logger.error(f"Failed to read recent signals: {e}")
        return signals


# Singleton instance
cross_bot_monitor = CrossBotMonitor()
