# zohra/services/chat/base_agent.py
from abc import ABC
from typing import Dict, Any, Optional

class ZohraBaseAgent(ABC):
    """
    Base class for all ZOHRA OS AI Agents.
    All agents (Trading, Research, Risk, Personal, etc.) inherit from this interface.
    """
    def __init__(self, agent_id: str, name: str, description: str):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.enabled = True

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state and metrics for the agent."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled
        }

    def on_event(self, event_type: str, data: Any):
        """Processes events dispatched from the event bus."""
        pass
