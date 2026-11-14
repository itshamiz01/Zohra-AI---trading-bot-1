import logging
from typing import List, Dict, Any
from zohra.db.schema import db

logger = logging.getLogger("zohra.services.chat.session")

class SessionManager:
    """
    Manages user sessions, context windows, and database persistence
    for the trading command center conversational interface.
    """

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch past messages in chronological order for the session."""
        try:
            return db.get_chat_history(session_id, limit=limit)
        except Exception as e:
            logger.error(f"Error getting session history: {e}")
            return []

    def add_message(self, session_id: str, role: str, message: str,
                    intent: str = None, parameters: dict = None) -> bool:
        """Persist a message in the chat history database."""
        try:
            return db.log_chat_message(
                session_id=session_id,
                role=role,
                message=message,
                intent=intent,
                parameters=parameters
            )
        except Exception as e:
            logger.error(f"Error logging chat message: {e}")
            return False

    def get_session_context(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Fetch chat history and format it as a list of message dicts
        compatible with OpenAI/Groq API expectations (role + content).
        """
        history = self.get_history(session_id, limit=limit)
        context = []
        for msg in history:
            context.append({
                "role": msg.get("role", "user"),
                "content": msg.get("message", "")
            })
        return context
