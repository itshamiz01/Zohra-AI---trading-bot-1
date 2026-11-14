from datetime import datetime, timedelta
from typing import Dict, List, Any
from zohra.core.agent_message import AgentMessage
from zohra.core.enums import NewsStatus
from zohra.integrations.news import NewsAnalyzer

class NewsAgent:
    """
    News Intelligence Agent:
    - Monitors the economic calendar (CPI, NFP, FOMC, Central Bank speeches, Geopolitical events).
    - Votes APPROVE or VETO on active trade proposals based on news blackout windows.
    """
    def __init__(self, news_analyzer: NewsAnalyzer = None):
        self.news_analyzer = news_analyzer or NewsAnalyzer()
        # Events are loaded from a configured provider or explicitly supplied
        # by an operator.  Historical sample events must never influence a
        # live trading vote.
        self.scheduled_events = []

    def add_event(self, event_name: str, currency: str, event_time: str, before: int = 30, after: int = 30):
        """Add a specific high-impact event to the calendar."""
        self.scheduled_events.append({
            "event": event_name,
            "currency": currency,
            "time": event_time,
            "before": before,
            "after": after
        })

    def check_news_status(self, symbol: str, dt_now: datetime = None) -> Dict[str, Any]:
        """
        Check if there are any high-impact news events blocking trading for the symbol.
        Returns status ('CLEAR', 'BLACKOUT') and the event description if blocked.
        """
        dt_now = dt_now or datetime.utcnow()
        
        # Determine affected currencies for the symbol
        currencies = ["ALL"]
        if len(symbol) >= 6:
            currencies.append(symbol[:3].upper()) # e.g. EUR
            currencies.append(symbol[3:6].upper()) # e.g. USD
        else:
            currencies.append(symbol.upper())
        
        # Check explicit news_analyzer blackout windows first
        if hasattr(self.news_analyzer, "get_status"):
            status = self.news_analyzer.get_status(symbol, dt_now)
            if status in (NewsStatus.BLACKOUT, NewsStatus.HIGH_IMPACT, "BLACKOUT", "HIGH_IMPACT", "blackout", "high_impact"):
                reason = f"News analyzer reported high impact news status: {getattr(status, 'value', str(status))}"
                if hasattr(self.news_analyzer, "get_active_event"):
                    event = self.news_analyzer.get_active_event(symbol, dt_now)
                    if event:
                        reason = f"High-Impact news [{event['title']}] for {event['country']} at {event['time'].strftime('%Y-%m-%d %H:%M:%S')} UTC (Blackout window ±30m)"
                return {
                    "status": "BLACKOUT",
                    "reason": reason
                }

        # Check local scheduled events list
        for item in self.scheduled_events:
            if item["currency"] in currencies:
                try:
                    event_dt = datetime.fromisoformat(item["time"])
                except ValueError:
                    continue
                before_dt = event_dt - timedelta(minutes=item["before"])
                after_dt = event_dt + timedelta(minutes=item["after"])
                
                if before_dt <= dt_now <= after_dt:
                    return {
                        "status": "BLACKOUT",
                        "reason": f"High-Impact event [{item['event']}] at {item['time']} (UTC). Current time {dt_now.isoformat()} is within the blackout window (-{item['before']}m / +{item['after']}m)."
                    }
                    
        return {"status": "CLEAR", "reason": "No high impact news events detected."}

    def evaluate_proposal(self, message: AgentMessage) -> AgentMessage:
        """
        Listens to a trade proposal and generates a VOTE message.
        """
        payload = message.payload
        symbol = payload.get("symbol", "EURUSD")
        proposal_id = message.message_id
        
        # Check news status
        news_check = self.check_news_status(symbol)
        
        vote_type = "APPROVE"
        reason = "Economic calendar is clear. No high-impact events nearby."
        
        if news_check["status"] == "BLACKOUT":
            vote_type = "VETO"
            reason = news_check["reason"]
            
        vote_payload = {
            "proposal_id": proposal_id,
            "vote": vote_type,
            "lots": None,
            "reason": reason
        }
        
        return AgentMessage(
            sender="NewsAgent",
            message_type="VOTE",
            payload=vote_payload
        )
