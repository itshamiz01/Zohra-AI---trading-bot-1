"""
Economic news calendar feed integration.
Fetches high-impact news events dynamically and flags blackout windows.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import threading
import requests

from zohra.core.enums import NewsStatus

logger = logging.getLogger("zohra.news")


class NewsAnalyzer:
    """
    Scrapes the Faireconomy XML economic calendar weekly feed.
    Caches events for 1 hour to prevent IP blocking/rate limits.
    """

    def __init__(self, blackout_windows: Optional[List[Dict]] = None):
        self.blackout_windows = blackout_windows or []
        self._cached_events: List[Dict] = []
        self._last_fetch_time: Optional[datetime] = None
        self._lock = threading.Lock()

    def _parse_event_time(self, date_str: str, time_str: str) -> Optional[datetime]:
        """
        Parses date (MM-DD-YYYY) and time (e.g. 9:15am, 10:30pm) from feed,
        converts from Eastern Time (EST/EDT) to UTC.
        """
        time_clean = time_str.lower().strip()
        # Skip events with no clear time (e.g., 'All Day', 'Day 1')
        if not (time_clean.endswith("am") or time_clean.endswith("pm")):
            return None

        try:
            parts = time_clean[:-2].split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            
            if "pm" in time_clean and hh < 12:
                hh += 12
            if "am" in time_clean and hh == 12:
                hh = 0

            date_parts = date_str.split("-")
            month = int(date_parts[0])
            day = int(date_parts[1])
            year = int(date_parts[2])

            # EST = UTC-5, EDT = UTC-4
            # DST check: Eastern Daylight Time is active from second Sunday in March to first Sunday in November
            is_dst = False
            if 3 < month < 11:
                is_dst = True
            elif month == 3:
                is_dst = day >= 14
            elif month == 11:
                is_dst = day < 7

            offset_hours = -4 if is_dst else -5
            dt_est = datetime(year, month, day, hh, mm)
            dt_utc = dt_est - timedelta(hours=offset_hours)
            return dt_utc.replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.debug(f"Failed to parse news event time date='{date_str}' time='{time_str}': {e}")
            return None

    def fetch_calendar(self) -> List[Dict]:
        """Fetch the XML feed and parse events."""
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        try:
            logger.info("Fetching weekly economic calendar from Faireconomy...")
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                events = []
                for elem in root.findall("event"):
                    title = elem.findtext("title")
                    country = elem.findtext("country")
                    date_str = elem.findtext("date")
                    time_str = elem.findtext("time")
                    impact = elem.findtext("impact")
                    
                    if not (title and country and date_str and time_str and impact):
                        continue
                        
                    event_utc = self._parse_event_time(date_str, time_str)
                    if event_utc:
                        events.append({
                            "title": title,
                            "country": country.upper().strip(),
                            "time": event_utc,
                            "impact": impact.strip().lower()
                        })
                logger.info(f"Loaded {len(events)} events from dynamic calendar feed.")
                return events
            else:
                logger.warning(f"Economic calendar feed returned status {resp.status_code}")
        except Exception as e:
            logger.error(f"Error fetching economic calendar: {e}")
        return []

    def _ensure_fresh_calendar(self):
        """Ensure news data cache is fresh (re-fetch hourly)."""
        now = datetime.utcnow()
        if (self._last_fetch_time is None or 
                now - self._last_fetch_time > timedelta(hours=1) or 
                not self._cached_events):
            with self._lock:
                # Double-check inside lock
                if (self._last_fetch_time is None or 
                        now - self._last_fetch_time > timedelta(hours=1) or 
                        not self._cached_events):
                    events = self.fetch_calendar()
                    if events:
                        self._cached_events = events
                        self._last_fetch_time = now
                    elif not self._cached_events:
                        # If fetch failed and we have no cached data, set fallback empty state
                        self._cached_events = []
                        self._last_fetch_time = now - timedelta(minutes=45) # try again sooner

    def get_status(self, symbol: str, dt: Optional[datetime] = None) -> NewsStatus:
        """
        Check if there are any active blackout windows for the symbol.
        Blackout is active within 30 minutes of high-impact events.
        """
        self._ensure_fresh_calendar()

        if dt is None:
            dt = datetime.utcnow().replace(tzinfo=timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Extract base currencies to monitor (e.g. EURUSD -> EUR, USD)
        currencies = ["ALL"]
        if len(symbol) >= 6:
            currencies.append(symbol[:3].upper())
            currencies.append(symbol[3:6].upper())
        else:
            currencies.append(symbol.upper())

        # 1. Check dynamic live economic calendar
        for event in self._cached_events:
            if event["country"] in currencies:
                # We veto on high impact events
                if event["impact"] == "high":
                    start_blackout = event["time"] - timedelta(minutes=30)
                    end_blackout = event["time"] + timedelta(minutes=30)
                    if start_blackout <= dt <= end_blackout:
                        logger.warning(f"Economic blackout active for {symbol} due to [{event['title']}] ({event['country']}) at {event['time'].isoformat()}")
                        return NewsStatus.BLACKOUT

        # 2. Fallback to manual configured windows
        for window in self.blackout_windows:
            if window.get("currency") in currencies:
                start = window.get("start")
                end = window.get("end")
                # Parse strings to offset-aware datetimes
                try:
                    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
                    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
                    if start_dt <= dt <= end_dt:
                        impact = window.get("impact", "high")
                        return NewsStatus.BLACKOUT if impact == "high" else NewsStatus.HIGH_IMPACT
                except Exception:
                    continue

        return NewsStatus.CLEAR

    def is_trade_allowed(self, symbol: str) -> bool:
        """Helper checking if trading is permitted."""
        return self.get_status(symbol) not in (NewsStatus.BLACKOUT, NewsStatus.HIGH_IMPACT)

    def get_active_event(self, symbol: str, dt: Optional[datetime] = None) -> Optional[Dict]:
        """Get the active high-impact event causing the blackout, if any."""
        self._ensure_fresh_calendar()

        if dt is None:
            dt = datetime.utcnow().replace(tzinfo=timezone.utc)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        currencies = ["ALL"]
        if len(symbol) >= 6:
            currencies.append(symbol[:3].upper())
            currencies.append(symbol[3:6].upper())
        else:
            currencies.append(symbol.upper())

        for event in self._cached_events:
            if event["country"] in currencies:
                if event["impact"] == "high":
                    start_blackout = event["time"] - timedelta(minutes=30)
                    end_blackout = event["time"] + timedelta(minutes=30)
                    if start_blackout <= dt <= end_blackout:
                        return event
        return None
