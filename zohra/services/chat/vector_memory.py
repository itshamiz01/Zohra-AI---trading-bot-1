# zohra/services/chat/vector_memory.py
import uuid
import logging
from typing import List, Dict, Any, Optional
from zohra.memory.vector_store import ai_memory

logger = logging.getLogger("zohra.services.chat.vector_memory")

class VectorMemoryManager:
    """
    Manages long-term semantic memory queries and storage for user preferences,
    strategy analyses, and past conversational context.
    """
    def add_preference_or_insight(self, text: str, category: str = "general", metadata: Optional[dict] = None) -> str:
        """Store a semantic memory in the vector store."""
        memory_id = f"MEM_{uuid.uuid4().hex[:8].upper()}"
        meta = metadata or {}
        meta["type"] = "user_preference_insight"
        
        try:
            ai_memory.add_trade_experience(
                trade_id=memory_id,
                context_text=text,
                category=category,
                metadata=meta
            )
            logger.info(f"Logged semantic memory: {memory_id} under category {category}")
            return memory_id
        except Exception as e:
            logger.error(f"Failed to save long-term memory: {e}")
            return ""

    def query_semantic_memories(self, query_text: str, category: Optional[str] = None, limit: int = 3) -> str:
        """
        Queries semantic long-term memories and returns a formatted context
        string for the agent's context window.
        """
        try:
            memories = ai_memory.query_experience(query_text, category=category, limit=limit)
            if not memories:
                return ""
                
            formatted_memories = []
            for mem in memories:
                score = mem.get("score", 0.0)
                text = mem.get("text", "")
                cat = mem.get("metadata", {}).get("category", "general")
                formatted_memories.append(f"- [{cat} memory] {text} (Relevance: {score})")
                
            ctx_str = "\n".join(formatted_memories)
            return f"\nRelevant long-term memories retrieved:\n{ctx_str}\n"
        except Exception as e:
            logger.error(f"Failed to query semantic memories: {e}")
            return ""

# Singleton
vector_memory = VectorMemoryManager()
