"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — COGNITIVE MEMORY STORE                     ║
║         Persistent Episodic Memories & Timeline Indexing             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.memory.cognitive")

class CognitiveMemory:
    """
    Manages Zohra's long-term cognitive memory, including episodic memories
    (summaries of complete experiences) and a chronological timeline index.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes SQLite tables for episodic memory and timeline index."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. Cognitive Episodes (summaries of complete tasks/events)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cognitive_episodes (
                        id TEXT PRIMARY KEY,
                        domain TEXT NOT NULL, -- 'TRADING', 'RESEARCH', 'LEARNING', 'PERSONAL'
                        goal TEXT,
                        actions_json TEXT, -- JSON array of actions taken
                        outcome TEXT,
                        created_at TEXT
                    )
                """)
                
                # 2. Memory Timeline (chronological index of all major events)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS memory_timeline (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL, -- 'TRADE_CLOSED', 'RESEARCH_COMPLETED', 'MISTAKE_DETECTED'
                        description TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        reference_id TEXT
                    )
                """)
                
                # Create index on timeline timestamp for fast retrieval
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_timeline_timestamp ON memory_timeline(timestamp)")
                
                conn.commit()
            logger.info("Cognitive Memory database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Cognitive Memory database: {e}")

    def add_episode(self, episode_id: str, domain: str, goal: str, actions: List[str], outcome: str) -> bool:
        try:
            actions_json = json.dumps(actions)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO cognitive_episodes (id, domain, goal, actions_json, outcome, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (episode_id, domain, goal, actions_json, outcome, datetime.utcnow().isoformat()))
                conn.commit()
            logger.info(f"💾 Cognitive Episode saved: {episode_id} | Domain: {domain}")
            return True
        except Exception as e:
            logger.error(f"Failed to add cognitive episode: {e}")
            return False

    def add_timeline_event(self, event_type: str, description: str, reference_id: str = "") -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO memory_timeline (event_type, description, timestamp, reference_id)
                    VALUES (?, ?, ?, ?)
                """, (event_type, description, datetime.utcnow().isoformat(), reference_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add timeline event: {e}")
            return False

    def get_timeline(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM memory_timeline ORDER BY timestamp DESC LIMIT ?", (limit,))
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get memory timeline: {e}")
        return results

    def search_episodes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        results = []
        try:
            q = f"%{query}%"
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM cognitive_episodes 
                    WHERE goal LIKE ? OR outcome LIKE ? 
                    ORDER BY created_at DESC LIMIT ?
                """, (q, q, limit))
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to search cognitive episodes: {e}")
        return results

# Singleton
cognitive_memory = CognitiveMemory()
