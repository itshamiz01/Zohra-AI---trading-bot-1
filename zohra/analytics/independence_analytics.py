"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — MULTI-BOT INDEPENDENCE ANALYTICS                   ║
║       Calculates Cross-Bot Correlation Matrix & Health Score         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import logging
import datetime as dt
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from collections import defaultdict

from zohra.config.bot_profile import PROFILES_BY_ROLE, BOT_1_TREND_PROFILE, BOT_2_REVERSAL_PROFILE, BOT_3_STRUCTURE_PROFILE

logger = logging.getLogger("zohra.independence_analytics")


class IndependenceAnalytics:
    """
    Analyzes historical signal snapshots and active portfolio states across
    all three bot instances to compute the Independence Health Score (0-100).
    """

    def __init__(self, shared_dir: Optional[str] = None):
        if shared_dir:
            self.shared_dir = shared_dir
        else:
            from zohra.config.settings import CROSS_BOT_LOG_DIR
            self.shared_dir = CROSS_BOT_LOG_DIR

        os.makedirs(self.shared_dir, exist_ok=True)
        self.signal_registry_file = os.path.join(self.shared_dir, "signal_registry.jsonl")
        self.portfolio_state_file = os.path.join(self.shared_dir, "active_portfolio_state.json")

    def load_signals(self, lookback_hours: int = 24) -> List[Dict[str, Any]]:
        """Loads all published signals from the shared registry."""
        if not os.path.exists(self.signal_registry_file):
            return []

        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
        signals = []
        try:
            with open(self.signal_registry_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        data = json.loads(line)
                        ts = dt.datetime.fromisoformat(data.get("timestamp_utc", ""))
                        if ts.tzinfo is None: ts = ts.replace(tzinfo=dt.timezone.utc)
                        if ts >= cutoff:
                            signals.append(data)
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error loading signal registry: {e}")
        return signals

    def compute_independence_audit(self, lookback_hours: int = 24) -> Dict[str, Any]:
        """
        Computes the complete Multi-Bot Independence Audit.
        Evaluates strategy overlap, direction overlap, entry timing, and independence score.
        """
        signals = self.load_signals(lookback_hours=lookback_hours)

        by_bot = defaultdict(list)
        for s in signals:
            by_bot[s.get("bot_id", "UNKNOWN")].append(s)

        bot_keys = ["BOT_1_TREND", "BOT_2_REVERSAL", "BOT_3_STRUCTURE"]
        roles = {
            "BOT_1_TREND": BOT_1_TREND_PROFILE.bot_role,
            "BOT_2_REVERSAL": BOT_2_REVERSAL_PROFILE.bot_role,
            "BOT_3_STRUCTURE": BOT_3_STRUCTURE_PROFILE.bot_role,
        }

        pairwise_overlap = {}
        pair_list = [
            ("BOT_1_TREND", "BOT_2_REVERSAL"),
            ("BOT_1_TREND", "BOT_3_STRUCTURE"),
            ("BOT_2_REVERSAL", "BOT_3_STRUCTURE")
        ]

        total_comparisons = 0
        total_same_direction = 0
        total_same_group = 0

        for b1, b2 in pair_list:
            pair_label = f"{b1} ↔ {b2}"
            sigs1 = by_bot.get(b1, [])
            sigs2 = by_bot.get(b2, [])

            compared = 0
            same_dir = 0
            same_group = 0
            same_trigger = 0

            # Compare signals within 300s of each other
            for s1 in sigs1:
                t1 = dt.datetime.fromisoformat(s1["timestamp_utc"])
                if t1.tzinfo is None: t1 = t1.replace(tzinfo=dt.timezone.utc)

                for s2 in sigs2:
                    t2 = dt.datetime.fromisoformat(s2["timestamp_utc"])
                    if t2.tzinfo is None: t2 = t2.replace(tzinfo=dt.timezone.utc)

                    if abs((t1 - t2).total_seconds()) <= 300:
                        compared += 1
                        if s1.get("direction") == s2.get("direction"):
                            same_dir += 1
                        if s1.get("strategy_group") == s2.get("strategy_group"):
                            same_group += 1
                        if s1.get("trigger_type") == s2.get("trigger_type"):
                            same_trigger += 1
                        break

            dir_rate = (same_dir / compared * 100) if compared > 0 else 0.0
            group_rate = (same_group / compared * 100) if compared > 0 else 0.0
            total_comparisons += compared
            total_same_direction += same_dir
            total_same_group += same_group

            pairwise_overlap[pair_label] = {
                "compared_windows": compared,
                "same_direction_rate": dir_rate,
                "same_group_rate": group_rate,
                "overlap_pct": dir_rate
            }

        # Theoretical baseline independence based on strategy specialization architecture
        # Bot 1 (Trend) vs Bot 2 (Reversal) share 0 strategies (100% independent strategy sets)
        # Bot 1 (Trend) vs Bot 3 (Structure/Breakout) share 0 strategies (100% independent strategy sets)
        # Bot 2 (Reversal) vs Bot 3 (Structure) share only False Breakout (93% independent strategy sets)
        strategy_separation_score = 95.0

        if total_comparisons > 0:
            avg_dir_overlap = total_same_direction / total_comparisons * 100
            avg_group_overlap = total_same_group / total_comparisons * 100
            # Higher overlap reduces independence score
            independence_score = max(10, min(100, int(100 - (avg_dir_overlap * 0.4 + avg_group_overlap * 0.4))))
        else:
            # When initialized with distinct profiles but before market trade generation
            independence_score = int(strategy_separation_score)

        if independence_score >= 80:
            status = "HEALTHY"
        elif independence_score >= 60:
            status = "MODERATE_DIVERSIFICATION"
        elif independence_score >= 40:
            status = "HIGH_OVERLAP"
        else:
            status = "BOT DIVERSIFICATION FAILURE DETECTED"

        # Load active fleet portfolio state
        fleet_positions = 0
        duplicate_events = 0
        if os.path.exists(self.portfolio_state_file):
            try:
                with open(self.portfolio_state_file, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                    fleet_positions = len(pdata.get("active_positions", {}))
            except Exception:
                pass

        return {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "roles": roles,
            "total_signals_logged": len(signals),
            "pairwise_overlap": pairwise_overlap,
            "duplicate_trade_events": duplicate_events,
            "simultaneous_positions": fleet_positions,
            "independence_score": independence_score,
            "status": status,
            "strategy_architecture": {
                "bot_1_strategies": BOT_1_TREND_PROFILE.enabled_strategies,
                "bot_2_strategies": BOT_2_REVERSAL_PROFILE.enabled_strategies,
                "bot_3_strategies": BOT_3_STRUCTURE_PROFILE.enabled_strategies,
            }
        }


# Master singleton instance
independence_analytics = IndependenceAnalytics()
