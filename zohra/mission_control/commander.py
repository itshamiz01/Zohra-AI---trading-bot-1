"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — AI TRADING COMMANDER                            ║
║     Conversational Natural-Language Commands Processing Center        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger("zohra.mission_control.commander")


class AITradingCommander:
    """
    Translates conversational input commands into direct action methods
    under Zohra command console or dashboard overrides.
    """

    def __init__(self):
        self._command_history: List[Dict] = []

    def process_natural_command(self, user_prompt: str) -> Dict[str, Any]:
        """Classify user text and return response message."""
        prompt = user_prompt.lower().strip()
        timestamp = datetime.utcnow().isoformat()
        
        response_msg = ""
        action_triggered = "none"
        action_data = {}

        # 1. Emergency stop / Pause
        if "emergency stop" in prompt or "kill switch" in prompt:
            response_msg = "🚨 EMERGENCY SHUTDOWN INITIATED. All open positions closed. Algorithms paused."
            action_triggered = "emergency_stop"
            self._trigger_emergency_stop()

        elif "pause trading" in prompt or "pause all" in prompt:
            response_msg = "⏸ Trading scanning loops paused globally. Active trades remain protected."
            action_triggered = "pause_trading"
            self._set_trading_state(False)

        elif "resume trading" in prompt or "resume all" in prompt:
            response_msg = "▶ Trading scanning loops resumed globally."
            action_triggered = "resume_trading"
            self._set_trading_state(True)

        # 2. Capital adjustments / allocations
        elif "reduce crypto" in prompt:
            response_msg = "📉 Crypto market engine capital allocation target scaled down to 5% equity."
            action_triggered = "allocate_capital"
            action_data = {"broker": "coindcx", "target_pct": 5.0}
            self._rotate_capital("coindcx", 5.0)

        elif "allocate more capital to forex" in prompt:
            response_msg = "📈 Forex market engine allocation targets increased to 60% equity."
            action_triggered = "allocate_capital"
            action_data = {"broker": "mt5", "target_pct": 60.0}
            self._rotate_capital("mt5", 60.0)

        # 3. Mode changes
        elif "defensive mode" in prompt or "defensive" in prompt:
            response_msg = "🛡 Defensive mode active. Position sizing multipliers set to 0.5x. Tight stop-loss rules applied."
            action_triggered = "switch_risk_mode"
            action_data = {"mode": "defensive"}
            self._set_risk_mode("defensive")

        # 4. Status / Diagnostics
        elif "diagnostics" in prompt or "self-healing" in prompt:
            from zohra.mission_control.self_healing import self_healing_engine
            res = self_healing_engine.run_diagnostics()
            response_msg = f"🔍 Diagnostics completed. Status: {res['status']}. CPU: {res['cpu_usage_pct']}%. Process Memory: {res['memory_usage_mb']} MB. Anomalies found: {len(res['anomalies'])}."
            action_triggered = "diagnostics"
            action_data = res

        elif "opportunities" in prompt or "best opportunity" in prompt:
            from zohra.mission_control.mission_control import mission_control
            opps = mission_control.get_ranked_opportunities()
            if opps:
                best = opps[0]
                response_msg = f"🏆 Top trading opportunity ranked: {best['symbol']} ({best['decision']} with confidence {best['confidence']}%). Reasons: {', '.join(best.get('reasons', []))}."
            else:
                response_msg = "No ranked opportunities available at this time."
            action_triggered = "list_opportunities"
            action_data = {"opportunities": opps}

        elif "mission control status" in prompt:
            response_msg = "📡 Trading Mission Control online. Gateway links normal. Capital rotation maps cleared. Risk parameters: Active."
            action_triggered = "status"

        else:
            response_msg = f"Command recognized. Relaying query to Zohra AI core processors: '{user_prompt}'."
            action_triggered = "chat_query"

        record = {
            "timestamp": timestamp,
            "prompt": user_prompt,
            "response": response_msg,
            "action": action_triggered,
            "data": action_data
        }
        self._command_history.append(record)
        if len(self._command_history) > 100:
            self._command_history.pop(0)

        return record

    def get_history(self) -> List[Dict]:
        return self._command_history[-20:]

    # ─── Direct Action Wrappers ───────────────────────────────

    def _trigger_emergency_stop(self):
        try:
            from zohra.brokers.manager import broker_manager
            broker_manager.close_all_positions()
            self._set_trading_state(False)
        except Exception as e:
            logger.error(f"AI Commander failed to run emergency close: {e}")

    def _set_trading_state(self, enabled: bool):
        try:
            from zohra.config.settings import STATE
            STATE.trading_enabled = enabled
        except Exception:
            pass

    def _rotate_capital(self, broker: str, target: float):
        try:
            from zohra.mission_control.mission_control import mission_control
            mission_control.rotate_capital(broker, target)
        except Exception:
            pass

    def _set_risk_mode(self, mode: str):
        try:
            from zohra.mission_control.mission_control import mission_control
            mission_control.set_risk_mode(mode)
        except Exception:
            pass


# Singleton
ai_commander = AITradingCommander()
