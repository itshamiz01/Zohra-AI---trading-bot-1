"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — PERSONAL MEMORY STORE                      ║
║     Tasks, Goals, Habits, Notes & Reminders — SQLite Persistence     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.personal.memory")

class PersonalMemory:
    """
    Single SQLite store for all Personal Division data: tasks, goals,
    habits, notes, and reminders.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()

                # Tasks
                c.execute("""
                    CREATE TABLE IF NOT EXISTS personal_tasks (
                        id       INTEGER PRIMARY KEY AUTOINCREMENT,
                        title    TEXT    NOT NULL,
                        priority TEXT    DEFAULT 'MEDIUM',  -- HIGH / MEDIUM / LOW
                        status   TEXT    DEFAULT 'PENDING', -- PENDING / IN_PROGRESS / DONE
                        due_at   TEXT,
                        created_at TEXT
                    )
                """)

                # Goals
                c.execute("""
                    CREATE TABLE IF NOT EXISTS personal_goals (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        title        TEXT    NOT NULL,
                        category     TEXT    DEFAULT 'PERSONAL', -- FINANCIAL/HEALTH/LEARNING/BUSINESS
                        progress_pct REAL    DEFAULT 0.0,
                        due_at       TEXT,
                        created_at   TEXT
                    )
                """)

                # Habits
                c.execute("""
                    CREATE TABLE IF NOT EXISTS personal_habits (
                        id             INTEGER PRIMARY KEY AUTOINCREMENT,
                        name           TEXT    NOT NULL UNIQUE,
                        streak         INTEGER DEFAULT 0,
                        last_completed TEXT
                    )
                """)

                # Notes
                c.execute("""
                    CREATE TABLE IF NOT EXISTS personal_notes (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        title      TEXT    NOT NULL,
                        content    TEXT    NOT NULL,
                        tags       TEXT    DEFAULT '',
                        created_at TEXT
                    )
                """)

                # Reminders
                c.execute("""
                    CREATE TABLE IF NOT EXISTS personal_reminders (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        title     TEXT    NOT NULL,
                        remind_at TEXT,
                        is_done   INTEGER DEFAULT 0
                    )
                """)

                # Seed demo data if tables are empty
                c.execute("SELECT COUNT(*) FROM personal_tasks")
                if c.fetchone()[0] == 0:
                    now = datetime.utcnow().isoformat()
                    tasks = [
                        ("Review Trading Report", "HIGH",   "PENDING",     "2026-06-30", now),
                        ("Finalize Book Buddy Roadmap", "HIGH", "IN_PROGRESS", "2026-07-05", now),
                        ("Write LinkedIn Article on SMC", "MEDIUM", "PENDING", "2026-07-02", now),
                    ]
                    c.executemany(
                        "INSERT INTO personal_tasks (title,priority,status,due_at,created_at) VALUES (?,?,?,?,?)",
                        tasks
                    )

                c.execute("SELECT COUNT(*) FROM personal_goals")
                if c.fetchone()[0] == 0:
                    now = datetime.utcnow().isoformat()
                    goals = [
                        ("Reach $10k/month trading income", "FINANCIAL", 35.0, "2026-12-31", now),
                        ("Publish Book Buddy v1.0",          "BUSINESS",  20.0, "2026-09-30", now),
                        ("Read 24 books this year",          "LEARNING",  50.0, "2026-12-31", now),
                        ("Exercise 4x per week",             "HEALTH",    60.0, "2026-12-31", now),
                    ]
                    c.executemany(
                        "INSERT INTO personal_goals (title,category,progress_pct,due_at,created_at) VALUES (?,?,?,?,?)",
                        goals
                    )

                c.execute("SELECT COUNT(*) FROM personal_habits")
                if c.fetchone()[0] == 0:
                    habits = [
                        ("Morning Review",  7,  "2026-06-29"),
                        ("Deep Work Block", 4,  "2026-06-28"),
                        ("Reading",         12, "2026-06-29"),
                        ("Exercise",        3,  "2026-06-27"),
                    ]
                    c.executemany(
                        "INSERT INTO personal_habits (name,streak,last_completed) VALUES (?,?,?)",
                        habits
                    )

                conn.commit()
            logger.info("Personal Memory database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Personal Memory: {e}")

    # ── Tasks ─────────────────────────────────────────────────────────
    def add_task(self, title: str, priority: str = "MEDIUM", due_at: str = "") -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO personal_tasks (title,priority,status,due_at,created_at) VALUES (?,?,?,?,?)",
                    (title, priority.upper(), "PENDING", due_at, datetime.utcnow().isoformat())
                )
                conn.commit()
                return c.lastrowid or 0
        except Exception as e:
            logger.error(f"add_task failed: {e}")
            return 0

    def complete_task(self, task_id: int) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE personal_tasks SET status='DONE' WHERE id=?", (task_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"complete_task failed: {e}")
            return False

    def get_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                if status:
                    c.execute("SELECT * FROM personal_tasks WHERE status=? ORDER BY priority DESC", (status,))
                else:
                    c.execute("SELECT * FROM personal_tasks ORDER BY priority DESC")
                return [dict(r) for r in c.fetchall()]
        except Exception as e:
            logger.error(f"get_tasks failed: {e}")
            return []

    # ── Goals ─────────────────────────────────────────────────────────
    def add_goal(self, title: str, category: str = "PERSONAL", due_at: str = "") -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO personal_goals (title,category,progress_pct,due_at,created_at) VALUES (?,?,?,?,?)",
                    (title, category.upper(), 0.0, due_at, datetime.utcnow().isoformat())
                )
                conn.commit()
                return c.lastrowid or 0
        except Exception as e:
            logger.error(f"add_goal failed: {e}")
            return 0

    def update_goal_progress(self, goal_id: int, progress_pct: float) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE personal_goals SET progress_pct=? WHERE id=?", (progress_pct, goal_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_goal_progress failed: {e}")
            return False

    def get_goals(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM personal_goals ORDER BY category")
                return [dict(r) for r in c.fetchall()]
        except Exception as e:
            logger.error(f"get_goals failed: {e}")
            return []

    # ── Habits ────────────────────────────────────────────────────────
    def log_habit(self, name: str) -> bool:
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT id, streak, last_completed FROM personal_habits WHERE name=?", (name,))
                row = c.fetchone()
                if row:
                    habit_id, streak, last = row
                    new_streak = streak + 1 if last != today else streak
                    c.execute(
                        "UPDATE personal_habits SET streak=?, last_completed=? WHERE id=?",
                        (new_streak, today, habit_id)
                    )
                else:
                    c.execute(
                        "INSERT INTO personal_habits (name,streak,last_completed) VALUES (?,?,?)",
                        (name, 1, today)
                    )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"log_habit failed: {e}")
            return False

    def get_habits(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM personal_habits ORDER BY streak DESC")
                return [dict(r) for r in c.fetchall()]
        except Exception as e:
            logger.error(f"get_habits failed: {e}")
            return []

    # ── Notes ─────────────────────────────────────────────────────────
    def add_note(self, title: str, content: str, tags: str = "") -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO personal_notes (title,content,tags,created_at) VALUES (?,?,?,?)",
                    (title, content, tags, datetime.utcnow().isoformat())
                )
                conn.commit()
                return c.lastrowid or 0
        except Exception as e:
            logger.error(f"add_note failed: {e}")
            return 0

    def get_notes(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM personal_notes ORDER BY id DESC LIMIT 50")
                return [dict(r) for r in c.fetchall()]
        except Exception as e:
            logger.error(f"get_notes failed: {e}")
            return []

    # ── Reminders ─────────────────────────────────────────────────────
    def add_reminder(self, title: str, remind_at: str) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO personal_reminders (title,remind_at,is_done) VALUES (?,?,0)",
                    (title, remind_at)
                )
                conn.commit()
                return c.lastrowid or 0
        except Exception as e:
            logger.error(f"add_reminder failed: {e}")
            return 0

    def get_reminders(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM personal_reminders WHERE is_done=0 ORDER BY remind_at")
                return [dict(r) for r in c.fetchall()]
        except Exception as e:
            logger.error(f"get_reminders failed: {e}")
            return []

# Singleton
personal_memory = PersonalMemory()
