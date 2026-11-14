"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — SOCIAL MEDIA MEMORY STORE                  ║
║         Persistent Content Queues, Drafts, & Channel Analytics       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.social.memory")

class SocialMediaMemory:
    """
    Manages Zohra's persistent social media data, including the content queue,
    scheduled posts, and historical performance analytics.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes SQLite tables for content queue and analytics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1. Social Content Queue
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS social_content_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL, -- 'INSTAGRAM', 'YOUTUBE', 'X', 'LINKEDIN'
                        title TEXT NOT NULL,
                        body_content TEXT NOT NULL,
                        tags_json TEXT, -- JSON array of hashtags/keywords
                        status TEXT NOT NULL, -- 'DRAFT', 'PENDING_APPROVAL', 'SCHEDULED', 'PUBLISHED'
                        scheduled_for TEXT
                    )
                """)
                
                # 2. Channel Analytics
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS social_analytics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        views INTEGER DEFAULT 0,
                        engagement INTEGER DEFAULT 0,
                        timestamp TEXT NOT NULL
                    )
                """)
                
                # Seed default analytics if empty
                cursor.execute("SELECT COUNT(*) FROM social_analytics")
                if cursor.fetchone()[0] == 0:
                    now_str = datetime.utcnow().strftime('%Y-%m-%d')
                    analytics = [
                        ("YOUTUBE", 12400, 820, now_str),
                        ("INSTAGRAM", 8500, 640, now_str),
                        ("X", 25400, 1840, now_str),
                        ("LINKEDIN", 3200, 310, now_str)
                    ]
                    cursor.executemany("INSERT INTO social_analytics (platform, views, engagement, timestamp) VALUES (?, ?, ?, ?)", analytics)

                # Seed default content queue if empty
                cursor.execute("SELECT COUNT(*) FROM social_content_queue")
                if cursor.fetchone()[0] == 0:
                    queue = [
                        ("INSTAGRAM", "SMC Liquidity Pools", "Swipe to learn how order blocks validate sweeps.", json.dumps(["smc", "trading", "forex"]), "PENDING_APPROVAL", datetime.utcnow().isoformat()),
                        ("YOUTUBE", "Gold Scalping Live", "Watch how Zohra OS executes gold scalps during London overlap.", json.dumps(["gold", "scalping", "algotrading"]), "DRAFT", datetime.utcnow().isoformat())
                    ]
                    cursor.executemany("INSERT INTO social_content_queue (platform, title, body_content, tags_json, status, scheduled_for) VALUES (?, ?, ?, ?, ?, ?)", queue)

                conn.commit()
            logger.info("Social Media Memory database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Social Media Memory database: {e}")

    def add_content(self, platform: str, title: str, body: str, tags: List[str], 
                    status: str = "PENDING_APPROVAL", scheduled_for: str = "") -> int:
        try:
            tags_json = json.dumps(tags)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO social_content_queue (platform, title, body_content, tags_json, status, scheduled_for)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (platform.upper(), title, body, tags_json, status, scheduled_for))
                conn.commit()
                return cursor.lastrowid or 0
        except Exception as e:
            logger.error(f"Failed to add content to queue: {e}")
            return 0

    def update_content_status(self, content_id: int, status: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE social_content_queue 
                    SET status = ? 
                    WHERE id = ?
                """, (status, content_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update content status: {e}")
            return False

    def add_analytics(self, platform: str, views: int, engagement: int) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO social_analytics (platform, views, engagement, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (platform.upper(), views, engagement, datetime.utcnow().strftime('%Y-%m-%d')))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add analytics: {e}")
            return False

    def get_content_queue(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM social_content_queue ORDER BY id DESC")
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get content queue: {e}")
        return results

    def get_analytics(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM social_analytics ORDER BY id DESC")
                results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
        return results

# Singleton
social_memory = SocialMediaMemory()
