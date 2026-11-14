"""
╔══════════════════════════════════════════════════════════════════════╗
║                     ZOHRA — COGNITIVE MEMORY API                     ║
║         Unified Retrieval, Memorization, & Timeline Interface        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, List, Any, Optional
from zohra.core.cognitive_memory import cognitive_memory
from zohra.core.research_memory import research_memory
from zohra.core.knowledge_graph import knowledge_graph_engine

logger = logging.getLogger("zohra.memory.api")

class MemoryAPI:
    """
    Exposes a clean, unified API for Zohra's cognitive retrieval,
    concept linkage, and timeline indexing.
    """
    def recall(self, query: str, domain: str = None, limit: int = 5) -> Dict[str, Any]:
        """
        Performs a hybrid search (semantic vector search + episodic keyword search)
        to retrieve relevant context for any query.
        """
        logger.info(f"🔍 Recalling memory for query: '{query}'")
        
        # 1. Semantic Vector Search
        query_emb = research_memory.generate_simple_embedding(query)
        vector_results = research_memory.semantic_search(query_emb, limit=limit)
        
        # 2. Episodic Memory Search
        episodes = cognitive_memory.search_episodes(query, limit=limit)
        
        # Filter by domain if specified
        if domain:
            episodes = [e for e in episodes if e["domain"].upper() == domain.upper()]
            
        return {
            "query": query,
            "semantic_contexts": vector_results,
            "episodes": episodes,
            "total_recalled": len(vector_results) + len(episodes)
        }

    def memorize(self, episode_id: str, domain: str, goal: str, 
                 actions: List[str], outcome: str) -> bool:
        """
        Records a high-level cognitive experience (episode) and indexes it
        on the system timeline.
        """
        # Save episode
        success = cognitive_memory.add_episode(episode_id, domain, goal, actions, outcome)
        if success:
            # Add timeline event
            desc = f"Completed {domain} task: '{goal[:60]}...' | Outcome: {outcome[:60]}..."
            cognitive_memory.add_timeline_event(
                event_type=f"{domain.upper()}_COMPLETED",
                description=desc,
                reference_id=episode_id
            )
            
            # Also add to Knowledge Graph
            node_id = f"ep_{episode_id}"
            knowledge_graph_engine.add_node(node_id, goal[:30], "Episode", desc)
            knowledge_graph_engine.add_edge(domain.lower(), node_id, "contains")
            
        return success

    def get_timeline(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the chronological timeline of all indexed events."""
        return cognitive_memory.get_timeline(limit=limit)

# Singleton
memory_api = MemoryAPI()
