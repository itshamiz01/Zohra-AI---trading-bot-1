"""AI Agent integration interface — for Zohra assistant."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional
import json

from zohra.db.connection import get_db


class AgentBridge(ABC):
    """Bridge between Zohra AI assistant and trading engine."""

    @abstractmethod
    def process_command(self, command: str, context: Dict) -> Dict:
        ...

    @abstractmethod
    def get_market_context(self, symbol: str) -> Dict:
        ...


class ZohraAgentBridge(AgentBridge):
    """Default agent bridge — logs actions, delegates to engine services."""

    def __init__(self, broker=None, analytics=None):
        self.broker = broker
        self.analytics = analytics
        self.agent_id = "zohra_assistant"

    def process_command(self, command: str, context: Dict) -> Dict:
        action = self._classify_command(command)
        self._log_action(action, {"command": command, **(context or {})})

        if action == "crypto_analysis":
            from zohra.core.crypto_intelligence import crypto_intelligence

            data = crypto_intelligence.update_intelligence_metrics()
            status = "success" if data.get("status") == "success" else "unavailable"
            return {
                "command": command,
                "action": action,
                "status": status,
                "message": "Bitcoin analysis complete" if status == "success" else "Crypto intelligence is unavailable.",
                "data": data,
            }

        if action == "crypto_portfolio":
            from zohra.core.crypto_portfolio import crypto_portfolio_manager

            data = crypto_portfolio_manager.get_portfolio_status()
            status = "success" if data.get("status") == "success" else "unavailable"
            return {
                "command": command,
                "action": action,
                "status": status,
                "message": "Crypto portfolio compiled" if status == "success" else "Crypto portfolio data is unavailable.",
                "data": data,
            }

        return {"command": command, "action": action, "status": "received"}

    def get_market_context(self, symbol: str) -> Dict:
        ctx = {"symbol": symbol, "timestamp": datetime.utcnow().isoformat()}
        if self.broker:
            ctx["price"] = self.broker.get_current_price(symbol)
            ctx["positions"] = [p for p in self.broker.get_open_positions() if p["symbol"] == symbol]
        if self.analytics:
            ctx["analytics"] = self.analytics.daily()
        return ctx

    def _classify_command(self, command: str) -> str:
        cmd = command.lower()
        if "crypto" in cmd and any(word in cmd for word in ("analyze", "analysis", "bitcoin", "btc")):
            return "crypto_analysis"
        if "crypto" in cmd and "portfolio" in cmd:
            return "crypto_portfolio"
        if "status" in cmd:
            return "get_status"
        if "pause" in cmd or "stop" in cmd:
            return "pause_trading"
        if "resume" in cmd or "start" in cmd:
            return "resume_trading"
        if "report" in cmd:
            return "generate_report"
        if "close" in cmd:
            return "close_positions"
        return "unknown"

    def _log_action(self, action_type: str, payload: Dict):
        db = get_db()
        p = db.placeholder()
        with db.cursor() as cur:
            cur.execute(
                f"INSERT INTO agent_actions (timestamp, agent_id, action_type, payload) VALUES ({p}, {p}, {p}, {p})",
                [datetime.utcnow().isoformat(), self.agent_id, action_type, json.dumps(payload)],
            )
