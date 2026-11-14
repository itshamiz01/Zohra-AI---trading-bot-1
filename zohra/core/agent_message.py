from dataclasses import dataclass, field
from datetime import datetime
import uuid
from typing import Dict, Any

@dataclass
class AgentMessage:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = "MarketAnalysisAgent"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    message_type: str = "PROPOSAL"  # PROPOSAL, VOTE, EXECUTION, LOG
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the message to a serializable dictionary."""
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
            "payload": self.payload
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """Reconstruct the message from a dictionary."""
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            sender=data.get("sender", ""),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            message_type=data.get("message_type", "PROPOSAL"),
            payload=data.get("payload", {})
        )
