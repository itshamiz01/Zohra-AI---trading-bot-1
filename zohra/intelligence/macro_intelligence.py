"""
╔══════════════════════════════════════════════════════════════════════╗
║         ZOHRA — ECONOMIC & MACRO INTELLIGENCE ENGINE                 ║
║    Pluggable Calendar System with Event Impact Scoring              ║
╚══════════════════════════════════════════════════════════════════════╝

The AI should understand macro context before approving trades.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from zohra.intelligence.models import MacroEvent, EventImpact
from zohra.config.settings import INTELLIGENCE_MACRO_LOOKAHEAD_HOURS

logger = logging.getLogger("zohra.intelligence.macro")


# ════════════════════════════════════════════════════════════════
#  CALENDAR PROVIDER INTERFACE
# ════════════════════════════════════════════════════════════════

class CalendarProvider(ABC):
    """Abstract base class for economic calendar providers."""

    @abstractmethod
    def get_events(self, from_dt: datetime, to_dt: datetime) -> List[MacroEvent]:
        """Return events within the given time window."""
        ...

    @abstractmethod
    def get_events_for_asset(self, asset: str) -> List[MacroEvent]:
        """Return events affecting a specific asset."""
        ...


class StaticCalendarProvider(CalendarProvider):
    """
    Ships with a JSON file of major recurring events.
    Future providers (ForexFactory, Investing.com) will inherit CalendarProvider.
    """

    def __init__(self):
        self._events: List[Dict] = []
        self._load_calendar()

    def _load_calendar(self):
        cal_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "economic_calendar.json")
        try:
            with open(cal_path, "r", encoding="utf-8") as f:
                self._events = json.load(f)
            logger.info(f"📅 Loaded {len(self._events)} static macro events from calendar.")
        except Exception as e:
            logger.warning(f"Could not load economic calendar: {e}")
            self._events = []

    def get_events(self, from_dt: datetime, to_dt: datetime) -> List[MacroEvent]:
        """Return all known events (static calendar is not time-bound)."""
        return [self._to_macro_event(e) for e in self._events]

    def get_events_for_asset(self, asset: str) -> List[MacroEvent]:
        """Return events that affect a specific asset symbol."""
        results = []
        asset_upper = asset.upper()
        for e in self._events:
            affected = [a.upper() for a in e.get("affected_assets", [])]
            if asset_upper in affected:
                results.append(self._to_macro_event(e))
        return results

    @staticmethod
    def _to_macro_event(raw: Dict) -> MacroEvent:
        return MacroEvent(
            event_id=raw.get("event_id", ""),
            title=raw.get("title", ""),
            country=raw.get("country", ""),
            currency=raw.get("currency", ""),
            datetime_utc=raw.get("datetime_utc", ""),
            impact=raw.get("impact", "low"),
            previous=raw.get("previous", ""),
            forecast=raw.get("forecast", ""),
            actual=raw.get("actual", ""),
            affected_assets=raw.get("affected_assets", []),
            category=raw.get("category", "general"),
        )


# ════════════════════════════════════════════════════════════════
#  MACRO INTELLIGENCE ENGINE
# ════════════════════════════════════════════════════════════════

class MacroIntelligenceEngine:
    """
    Provides macroeconomic awareness to the trading intelligence layer.
    Checks for upcoming events, scores their impact, and recommends
    trade approval or blocking.
    """

    def __init__(self, provider: Optional[CalendarProvider] = None):
        self.provider = provider or StaticCalendarProvider()
        self.lookahead_hours = INTELLIGENCE_MACRO_LOOKAHEAD_HOURS

        # Impact severity weights
        self._impact_weights = {
            "low": 1,
            "medium": 3,
            "high": 7,
            "critical": 10,
        }

    # ─── Event Querying ───────────────────────────────────────

    def get_upcoming_events(self, hours_ahead: Optional[int] = None) -> List[MacroEvent]:
        """Return events within the lookahead window."""
        now = datetime.utcnow()
        window = timedelta(hours=hours_ahead or self.lookahead_hours)
        return self.provider.get_events(now, now + window)

    def get_events_for_asset(self, asset: str) -> List[MacroEvent]:
        """Return events affecting a specific asset."""
        return self.provider.get_events_for_asset(asset)

    # ─── Impact Scoring ───────────────────────────────────────

    def score_event_impact(self, event: MacroEvent) -> int:
        """Score an event's impact from 1 (low) to 10 (critical)."""
        return self._impact_weights.get(event.impact, 1)

    def aggregate_impact(self, events: List[MacroEvent]) -> Dict[str, Any]:
        """Compute aggregate impact from multiple events."""
        if not events:
            return {"total_score": 0, "max_impact": "none", "event_count": 0, "severity": "clear"}

        scores = [self.score_event_impact(e) for e in events]
        total = sum(scores)
        max_score = max(scores)

        severity = "clear"
        if max_score >= 10:
            severity = "blackout"
        elif max_score >= 7:
            severity = "high_risk"
        elif max_score >= 3:
            severity = "moderate_risk"
        elif max_score >= 1:
            severity = "low_risk"

        return {
            "total_score": total,
            "max_impact": events[scores.index(max_score)].impact if scores else "none",
            "event_count": len(events),
            "severity": severity,
            "events": [e.title for e in events],
        }

    # ─── Trade Clearance ──────────────────────────────────────

    def check_trade_clearance(self, symbol: str) -> Dict[str, Any]:
        """
        Check if trading is safe for a symbol given upcoming macro events.
        Returns clearance status and reasoning.
        """
        events = self.get_events_for_asset(symbol)
        impact = self.aggregate_impact(events)

        cleared = impact["severity"] in ("clear", "low_risk")
        reduced = impact["severity"] == "moderate_risk"

        result = {
            "symbol": symbol,
            "cleared": cleared,
            "reduced_size": reduced,
            "blocked": not cleared and not reduced,
            "severity": impact["severity"],
            "reason": "",
            "events": impact.get("events", []),
        }

        if cleared:
            result["reason"] = "No significant macro events. Safe to trade."
        elif reduced:
            result["reason"] = f"Moderate macro risk ({impact['event_count']} events). Reduce position size."
        else:
            result["reason"] = f"High macro risk ({impact['severity']}). Trading blocked for {symbol}."

        return result

    # ─── Central Bank Tracking ────────────────────────────────

    def get_central_bank_events(self) -> List[MacroEvent]:
        """Return central bank related events."""
        all_events = self.get_upcoming_events(hours_ahead=168)  # 1 week
        return [e for e in all_events if e.category in ("interest_rate", "central_bank")]

    # ─── Macro Context Summary ────────────────────────────────

    def get_macro_summary(self) -> Dict[str, Any]:
        """Return a summary of the current macro landscape."""
        all_events = self.get_upcoming_events(hours_ahead=48)
        impact = self.aggregate_impact(all_events)
        cb_events = [e for e in all_events if e.category in ("interest_rate", "central_bank")]

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_events": len(all_events),
            "aggregate_severity": impact["severity"],
            "central_bank_events": len(cb_events),
            "high_impact_events": [e.title for e in all_events if e.impact in ("high", "critical")],
            "recommendation": "Caution" if impact["severity"] in ("high_risk", "blackout") else "Normal",
        }


# Singleton
macro_engine = MacroIntelligenceEngine()
