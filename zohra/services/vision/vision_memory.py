# ZOHRA OS — Visual Memory Manager
import sqlite3
import logging
import os
from typing import Dict, Any, List

logger = logging.getLogger("zohra.vision.memory")
DB_PATH = "logs/zohra_trades_c.db"

def init_vision_db():
    """Initializes the visual memory tables."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Screenshots Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visual_screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                monitor_id INTEGER,
                filepath TEXT NOT NULL,
                active_window_title TEXT
            )
        """)
        
        # 2. OCR Index Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visual_ocr_index (
                screenshot_id INTEGER,
                text_content TEXT,
                confidence REAL,
                FOREIGN KEY(screenshot_id) REFERENCES visual_screenshots(id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Visual Memory tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Visual Memory database: {e}")

class VisualMemoryManager:
    """Manages saving and searching visual memory frames and OCR index."""
    def __init__(self):
        init_vision_db()

    def store_screenshot(self, filepath: str, window_title: str, ocr_blocks: List[Dict[str, Any]], monitor_id: int = 0):
        """Stores a screenshot metadata and its OCR text index."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Save screenshot entry
            cursor.execute("""
                INSERT INTO visual_screenshots (monitor_id, filepath, active_window_title)
                VALUES (?, ?, ?)
            """, (monitor_id, filepath, window_title))
            screenshot_id = cursor.lastrowid
            
            # Index all OCR text
            full_text = " ".join([b["text"] for b in ocr_blocks])
            if full_text.strip():
                avg_conf = sum([b["confidence"] for b in ocr_blocks]) / len(ocr_blocks) if ocr_blocks else 1.0
                cursor.execute("""
                    INSERT INTO visual_ocr_index (screenshot_id, text_content, confidence)
                    VALUES (?, ?, ?)
                """, (screenshot_id, full_text, avg_conf))
                
            conn.commit()
            conn.close()
            logger.info(f"Stored visual memory: ID={screenshot_id}, Title='{window_title}'")
        except Exception as e:
            logger.error(f"Failed to store visual memory: {e}")

    def search_visual_memory(self, query: str) -> List[Dict[str, Any]]:
        """Searches visual memory by OCR text content."""
        results = []
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.timestamp, s.filepath, s.active_window_title, o.text_content
                FROM visual_screenshots s
                JOIN visual_ocr_index o ON s.id = o.screenshot_id
                WHERE o.text_content LIKE ?
                ORDER BY s.timestamp DESC
            """, (f"%{query}%",))
            
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "filepath": row[2],
                    "window_title": row[3],
                    "ocr_text": row[4]
                })
            conn.close()
        except Exception as e:
            logger.error(f"Failed to search visual memory: {e}")
        return results

    def write_visual_memory(self, structured_summary: str, source_context: str):
        """
        Writes structured vision output to episodic memory (V7.8).
        Structured output only — never raw pixels — consistent with V7.7's
        persistence rule. Goes through the SAME episodic memory path as
        conversational reflection (V3.9, V4.4.2) to avoid a separate
        'visual memories' silo.
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            content = f"Observed via {source_context}: {structured_summary}"

            cursor.execute("""
                INSERT INTO visual_screenshots (monitor_id, filepath, active_window_title)
                VALUES (?, ?, ?)
            """, (0, "[structured_only]", source_context))
            screenshot_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO visual_ocr_index (screenshot_id, text_content, confidence)
                VALUES (?, ?, ?)
            """, (screenshot_id, content, 1.0))

            conn.commit()
            conn.close()
            logger.info(f"Visual memory written: source={source_context}, len={len(content)}")
        except Exception as e:
            logger.error(f"Failed to write visual memory: {e}")

