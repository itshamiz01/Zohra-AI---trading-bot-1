# ZOHRA OS — Voice Memory & Pronunciation Engine
import sqlite3
import logging
import os
import re
from typing import Dict, Any

logger = logging.getLogger("zohra.voice.memory")

# Use the same SQLite database as the main trading bot
DB_PATH = "logs/zohra_trades_c.db"

def init_voice_db():
    """Initializes voice preference and pronunciation lexicon tables."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Voice Preferences Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voice_preferences (
                username TEXT PRIMARY KEY,
                speaking_speed REAL DEFAULT 1.0,
                response_length_pref TEXT DEFAULT 'balanced',
                preferred_voice_id TEXT DEFAULT '21m00Tcm4TlvDq8ikWAM',
                preferred_language TEXT DEFAULT 'en'
            )
        """)
        
        # 2. Pronunciation Lexicon Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pronunciation_lexicon (
                word TEXT PRIMARY KEY,
                spoken_equivalent TEXT NOT NULL,
                category TEXT DEFAULT 'general'
            )
        """)
        
        # Seed default pronunciations for trading symbols and technical terms
        default_lexicon = [
            ("XAUUSD", "Gold Spot Dollar", "symbol"),
            ("EURUSD", "Euro Dollar", "symbol"),
            ("USDJPY", "Dollar Yen", "symbol"),
            ("GBPUSD", "Pound Dollar", "symbol"),
            ("EMA", "Exponential Moving Average", "technical"),
            ("SMA", "Simple Moving Average", "technical"),
            ("PnL", "Profit and Loss", "technical"),
            ("MT5", "MetaTrader Five", "technical")
        ]
        
        for word, spoken, cat in default_lexicon:
            cursor.execute("""
                INSERT OR IGNORE INTO pronunciation_lexicon (word, spoken_equivalent, category)
                VALUES (?, ?, ?)
            """, (word, spoken, cat))
            
        conn.commit()
        conn.close()
        logger.info("Voice Memory & Pronunciation tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Voice Memory database: {e}")

class VoiceMemoryEngine:
    """Handles loading/saving user voice preferences and applying pronunciation replacements."""
    def __init__(self):
        init_voice_db()
        self.pronunciation_cache = self._load_pronunciation_lexicon()
        
    def _load_pronunciation_lexicon(self) -> Dict[str, str]:
        cache = {}
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT word, spoken_equivalent FROM pronunciation_lexicon")
            for row in cursor.fetchall():
                cache[row[0].lower()] = row[1]
            conn.close()
        except Exception as e:
            logger.error(f"Failed to load pronunciation lexicon: {e}")
        return cache

    def get_preferences(self, username: str) -> Dict[str, Any]:
        prefs = {
            "speaking_speed": 1.0,
            "response_length_pref": "balanced",
            "preferred_voice_id": "21m00Tcm4TlvDq8ikWAM",
            "preferred_language": "en"
        }
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT speaking_speed, response_length_pref, preferred_voice_id, preferred_language 
                FROM voice_preferences WHERE username = ?
            """, (username,))
            row = cursor.fetchone()
            if row:
                prefs = {
                    "speaking_speed": row[0],
                    "response_length_pref": row[1],
                    "preferred_voice_id": row[2],
                    "preferred_language": row[3]
                }
            conn.close()
        except Exception as e:
            logger.error(f"Failed to fetch voice preferences for {username}: {e}")
        return prefs

    def save_preferences(self, username: str, prefs: Dict[str, Any]):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO voice_preferences (username, speaking_speed, response_length_pref, preferred_voice_id, preferred_language)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    speaking_speed = excluded.speaking_speed,
                    response_length_pref = excluded.response_length_pref,
                    preferred_voice_id = excluded.preferred_voice_id,
                    preferred_language = excluded.preferred_language
            """, (
                username, 
                prefs.get("speaking_speed", 1.0), 
                prefs.get("response_length_pref", "balanced"),
                prefs.get("preferred_voice_id", "21m00Tcm4TlvDq8ikWAM"),
                prefs.get("preferred_language", "en")
            ))
            conn.commit()
            conn.close()
            logger.info(f"Voice preferences updated for user: {username}")
        except Exception as e:
            logger.error(f"Failed to save voice preferences for {username}: {e}")

    def apply_pronunciation(self, text: str) -> str:
        """Replaces trading symbols and technical acronyms with their spoken equivalents."""
        if not text:
            return ""
            
        # Use regex word boundaries to replace terms case-insensitively
        for word, spoken in self.pronunciation_cache.items():
            pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
            text = pattern.sub(spoken, text)
            
        return text
