"""
╔══════════════════════════════════════════════════════════════════════╗
║         ZOHRA — CROSS-BOT SIGNAL REGISTRY & DUPLICATE SCORER         ║
║          Prevents Redundant Exposure Across Multi-Bot Fleet          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import logging
import time
import datetime as dt
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from zohra.core.strategy_fingerprint import StrategyFingerprint

logger = logging.getLogger("zohra.cross_bot_registry")


class CrossBotSignalRegistry:
    """
    Central shared registry tracking candidate and executed signals across all
    running ZOHRA bot instances (Bot 1 Trend, Bot 2 Reversal, Bot 3 Structure).
    Calculates DUPLICATE_EXPOSURE_SCORE (0-100) before any trade is opened.
    """

    def __init__(self, shared_dir: Optional[str] = None):
        if shared_dir:
            self.shared_dir = shared_dir
        else:
            from zohra.config.settings import CROSS_BOT_LOG_DIR
            self.shared_dir = CROSS_BOT_LOG_DIR

        os.makedirs(self.shared_dir, exist_ok=True)
        self.registry_file = os.path.join(self.shared_dir, "signal_registry.jsonl")
        self.history_cache: List[StrategyFingerprint] = []
        self._last_read_mtime = 0.0

        logger.info(f"📋 CrossBotSignalRegistry initialized. Registry file: {self.registry_file}")

    def publish_signal(self, fingerprint: StrategyFingerprint) -> bool:
        """
        Publishes a proposed signal fingerprint to the central shared registry.
        """
        try:
            with open(self.registry_file, "a", encoding="utf-8") as f:
                f.write(fingerprint.to_json() + "\n")
            logger.info(
                f"📡 [{fingerprint.bot_id}] Published signal to registry: {fingerprint.direction} {fingerprint.symbol} "
                f"via {fingerprint.strategy_name} ({fingerprint.trigger_type})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to publish signal to registry: {e}")
            return False

    def _sync_registry(self, max_age_seconds: int = 1800):
        """Reads recent signals from the shared registry file."""
        if not os.path.exists(self.registry_file):
            return

        try:
            mtime = os.path.getmtime(self.registry_file)
            if mtime <= self._last_read_mtime:
                return

            cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=max_age_seconds)
            fresh_list = []

            with open(self.registry_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        fp = StrategyFingerprint.from_dict(data)
                        ts = dt.datetime.fromisoformat(fp.timestamp_utc)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=dt.timezone.utc)
                        if ts >= cutoff:
                            fresh_list.append(fp)
                    except Exception:
                        continue

            self.history_cache = fresh_list
            self._last_read_mtime = mtime
        except Exception as e:
            logger.error(f"Error syncing signal registry: {e}")

    def get_recent_signals(self, window_seconds: int = 300, exclude_bot_id: Optional[str] = None) -> List[StrategyFingerprint]:
        """Returns signals published within the specified time window."""
        self._sync_registry(max_age_seconds=window_seconds * 2)
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=window_seconds)

        active = []
        for fp in self.history_cache:
            if exclude_bot_id and fp.bot_id == exclude_bot_id:
                continue
            ts = dt.datetime.fromisoformat(fp.timestamp_utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            if ts >= cutoff:
                active.append(fp)
        return active

    def calculate_duplicate_exposure_score(
        self,
        candidate: StrategyFingerprint,
        window_seconds: int = 300,
        price_proximity_usd: float = 1.50
    ) -> Tuple[int, str, List[Dict[str, Any]]]:
        """
        Calculates the DUPLICATE_EXPOSURE_SCORE (0 to 100) per Step 6 of specification:
          • Same direction:                   +25
          • Entry within price proximity:     +25 (e.g. <= $1.50 on Gold)
          • Signal within time window (300s): +20
          • Same strategy group:              +20
          • Same market thesis/trigger:       +10

        Tiers:
          • 0-30:   Independent
          • 31-60:  Moderate overlap
          • 61-100: High duplicate exposure (Blocked / Pruned by Portfolio Risk Engine)
        """
        recent_signals = self.get_recent_signals(window_seconds=window_seconds, exclude_bot_id=candidate.bot_id)

        if not recent_signals:
            return 0, "INDEPENDENT_NO_PEER_SIGNALS", []

        max_score = 0
        primary_match_reason = "INDEPENDENT"
        overlapping_matches = []

        for peer in recent_signals:
            score = 0
            breakdown = []

            # 1. Same Direction (+25)
            if peer.direction == candidate.direction:
                score += 25
                breakdown.append("Same direction (+25)")

            # 2. Entry Price Proximity (+25)
            price_diff = abs(peer.entry_price - candidate.entry_price)
            if price_diff <= price_proximity_usd:
                score += 25
                breakdown.append(f"Price proximity ${price_diff:.2f} <= ${price_proximity_usd:.2f} (+25)")

            # 3. Time Window (+20)
            t_cand = dt.datetime.fromisoformat(candidate.timestamp_utc)
            t_peer = dt.datetime.fromisoformat(peer.timestamp_utc)
            if t_cand.tzinfo is None: t_cand = t_cand.replace(tzinfo=dt.timezone.utc)
            if t_peer.tzinfo is None: t_peer = t_peer.replace(tzinfo=dt.timezone.utc)
            time_delta = abs((t_cand - t_peer).total_seconds())
            if time_delta <= window_seconds:
                score += 20
                breakdown.append(f"Time delta {time_delta:.0f}s <= {window_seconds}s (+20)")

            # 4. Same Strategy Group (+20)
            if peer.strategy_group == candidate.strategy_group:
                score += 20
                breakdown.append(f"Same strategy group '{peer.strategy_group}' (+20)")

            # 5. Same Market Thesis / Trigger (+10)
            if peer.trigger_type == candidate.trigger_type or peer.strategy_name == candidate.strategy_name:
                score += 10
                breakdown.append(f"Matching thesis '{peer.trigger_type}' (+10)")

            if score > max_score:
                max_score = score
                if score >= 61:
                    primary_match_reason = f"HIGH_DUPLICATE_EXPOSURE with {peer.bot_name} (Score={score})"
                elif score >= 31:
                    primary_match_reason = f"MODERATE_OVERLAP with {peer.bot_name} (Score={score})"
                else:
                    primary_match_reason = f"INDEPENDENT (Score={score})"

            overlapping_matches.append({
                "peer_bot_id": peer.bot_id,
                "peer_bot_name": peer.bot_name,
                "peer_strategy": peer.strategy_name,
                "peer_direction": peer.direction,
                "peer_price": peer.entry_price,
                "overlap_score": score,
                "breakdown": breakdown
            })

        return max_score, primary_match_reason, overlapping_matches


# Master singleton instance
cross_bot_signal_registry = CrossBotSignalRegistry()
