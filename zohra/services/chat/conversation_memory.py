# zohra/services/chat/conversation_memory.py
import logging
from typing import List, Dict, Any
from zohra.db.schema import db

logger = logging.getLogger("zohra.services.chat.session")

class ConversationMemoryManager:
    """
    Manages short-term conversation memory and sliding context windows
    for the Gemini agentic reasoning loop.
    """
    def __init__(self, limit: int = 15):
        self.limit = limit

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Fetch raw message logs from the database."""
        try:
            return db.get_chat_history(session_id, limit=self.limit) or []
        except Exception as e:
            logger.error(f"Error fetching session history: {e}")
            return []

    def add_message(self, session_id: str, role: str, message: str,
                    intent: str = None, parameters: dict = None) -> bool:
        """Persist a message to the database ledger."""
        try:
            import json
            param_str = json.dumps(parameters) if parameters else None
            return db.log_chat_message(
                session_id=session_id,
                role=role,
                message=message,
                intent=intent,
                parameters=param_str
            )
        except Exception as e:
            logger.error(f"Error logging chat message: {e}")
            return False

    def get_gemini_history(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves recent history and formats it for Gemini's history structure:
        [{'role': 'user'|'model', 'parts': [{'text': '...'}]}]
        """
        raw_history = self.get_history(session_id)
        formatted = []
        
        # Sort chronologically (get_chat_history usually returns reverse chronological or chronological)
        # Let's inspect get_chat_history if possible or assume reverse chronological (newest first)
        # We will sort it if it's descending
        if raw_history and raw_history[0].get("id", 0) > raw_history[-1].get("id", 0):
            raw_history = list(reversed(raw_history))
            
        for msg in raw_history:
            role = msg.get("role", "user")
            # Map database 'assistant' or 'bot' role to Gemini's 'model'
            model_role = "model" if role in ("assistant", "bot", "model") else "user"
            content = msg.get("message", "")
            
            # Skip empty contents to avoid validation errors
            if not content:
                continue
                
            formatted.append({
                "role": model_role,
                "parts": [{"text": content}]
            })
            
        return formatted

    def get_summary_context(self, session_id: str) -> str:
        """
        Creates a brief summary context string of any historical turns
        prior to our sliding window limits to keep the agent aware of long-term history.
        """
        # SQLite database extraction of all history except the recent ones
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            placeholder = db.placeholder()
            cursor.execute(
                f"SELECT role, message FROM chat_sessions WHERE session_id = {placeholder} ORDER BY id DESC LIMIT 50 OFFSET {self.limit}",
                [session_id]
            )
            rows = cursor.fetchall()
            if not rows:
                return ""
            
            # Format summarized overview
            rows = list(reversed(rows))
            turns = []
            for r in rows:
                role = "User" if r[0] == "user" else "Zohra"
                turns.append(f"{role}: {r[1][:100]}...")
            
            summary = "\n".join(turns)
            return f"\nSummary of older context:\n{summary}\n"
        except Exception as e:
            logger.warning(f"Could not construct summary context: {e}")
            return ""

# Singleton
conversation_memory = ConversationMemoryManager()
