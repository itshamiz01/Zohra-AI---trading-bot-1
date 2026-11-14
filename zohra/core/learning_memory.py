"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — LEARNING MEMORY STORE                      ║
║         Persistent Lessons, Mistakes, and Mastery Tracking           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Any
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.learning.memory")

class LearningMemory:
    """
    Manages the persistent storage of lessons learned, trading mistakes,
    and skill mastery progress in the SQLite database.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes all SQLite tables required for the Learning Division."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. Learning Lessons (from trades, research, or chats)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS learning_lessons (
                        id TEXT PRIMARY KEY,
                        source_type TEXT, -- 'TRADE', 'RESEARCH', 'CONVERSATION'
                        source_id TEXT,
                        category TEXT, -- 'Risk', 'Execution', 'SMC', 'Trend'
                        lesson_text TEXT,
                        created_at TEXT
                    )
                """)
                
                # 2. Detected Mistakes (from trading or planning)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS detected_mistakes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_id TEXT,
                        severity TEXT, -- 'CRITICAL', 'MAJOR', 'MINOR'
                        mistake_type TEXT, -- 'Chasing Price', 'Wider Stop', 'Overtrading'
                        description TEXT,
                        created_at TEXT
                    )
                """)
                
                # 3. Mastery Levels (tracking skill development)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS mastery_levels (
                        domain TEXT PRIMARY KEY, -- 'SMC', 'Risk Management', 'Python', 'FastAPI'
                        level TEXT, -- 'BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'EXPERT'
                        xp INTEGER
                    )
                """)
                
                # Initialize default mastery levels if empty
                cursor.execute("SELECT COUNT(*) FROM mastery_levels")
                if cursor.fetchone()[0] == 0:
                    domains = [
                        ("SMC", "BEGINNER", 0),
                        ("Risk Management", "BEGINNER", 0),
                        ("Python", "INTERMEDIATE", 1500),
                        ("FastAPI", "BEGINNER", 200),
                        ("Market Psychology", "BEGINNER", 0)
                    ]
                    cursor.executemany("INSERT INTO mastery_levels (domain, level, xp) VALUES (?, ?, ?)", domains)
                
                conn.commit()
            logger.info("Learning Memory database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Learning Memory database: {e}")

    def add_lesson(self, lesson_id: str, source_type: str, source_id: str, category: str, lesson_text: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO learning_lessons (id, source_type, source_id, category, lesson_text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (lesson_id, source_type, source_id, category, lesson_text, datetime.utcnow().isoformat()))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add lesson: {e}")
            return False

    def add_mistake(self, trade_id: str, severity: str, mistake_type: str, description: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO detected_mistakes (trade_id, severity, mistake_type, description, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (trade_id, severity, mistake_type, description, datetime.utcnow().isoformat()))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add mistake: {e}")
            return False

    def get_mistakes(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM detected_mistakes ORDER BY id DESC LIMIT ?", (limit,))
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get mistakes: {e}")
        return results

    def get_lessons(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM learning_lessons ORDER BY created_at DESC LIMIT ?", (limit,))
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get lessons: {e}")
        return results

    def update_mastery(self, domain: str, xp_gained: int) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get current XP
                cursor.execute("SELECT xp, level FROM mastery_levels WHERE domain = ?", (domain,))
                row = cursor.fetchone()
                if not row:
                    # Insert new domain
                    current_xp = 0
                    current_level = "BEGINNER"
                else:
                    current_xp, current_level = row
                
                new_xp = current_xp + xp_gained
                
                # Simple leveling logic (e.g., 500 XP per level)
                new_level = "BEGINNER"
                if new_xp >= 2000:
                    new_level = "EXPERT"
                elif new_xp >= 1000:
                    new_level = "ADVANCED"
                elif new_xp >= 400:
                    new_level = "INTERMEDIATE"
                    
                cursor.execute("""
                    INSERT OR REPLACE INTO mastery_levels (domain, level, xp)
                    VALUES (?, ?, ?)
                """, (domain, new_level, new_xp))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update mastery: {e}")
            return False

    def get_mastery(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM mastery_levels ORDER BY xp DESC")
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get mastery: {e}")
        return results

# Singleton
learning_memory = LearningMemory()
