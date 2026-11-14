"""Voice command integration — maps spoken commands to agent actions."""

from typing import Dict

from zohra.integrations.ai_agent import ZohraAgentBridge

VOICE_ALIASES = {
    "what's my status": "status",
    "show status": "status",
    "pause trading": "pause",
    "stop trading": "pause",
    "resume trading": "resume",
    "daily report": "report daily",
    "close all positions": "close all",
}


class VoiceCommandHandler:
    def __init__(self, agent_bridge: ZohraAgentBridge):
        self.agent = agent_bridge

    def handle(self, transcript: str) -> Dict:
        normalized = transcript.lower().strip()
        command = VOICE_ALIASES.get(normalized, normalized)
        return self.agent.process_command(command, {"source": "voice", "transcript": transcript})
