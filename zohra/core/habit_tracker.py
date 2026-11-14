"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — HABIT TRACKER                              ║
║         Streak Intelligence & Constructive Behaviour Analytics       ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import logging
from datetime import datetime
from typing import List, Dict, Any
from zohra.core.personal_memory import personal_memory

logger = logging.getLogger("zohra.personal.habit")

class HabitTracker:
    def log(self, habit_name: str) -> Dict[str, Any]:
        logger.info(f"🔥 Logging habit: '{habit_name}'")
        personal_memory.log_habit(habit_name)
        habits = personal_memory.get_habits()
        h = next((x for x in habits if x["name"] == habit_name), None)
        return {"habit": habit_name, "streak": h["streak"] if h else 1}

    def get_all(self) -> List[Dict[str, Any]]:
        return personal_memory.get_habits()

    def get_at_risk(self) -> List[Dict[str, Any]]:
        """Return habits whose last_completed is not today (streak at risk)."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        habits = personal_memory.get_habits()
        return [h for h in habits if h.get("last_completed", "") < today]

habit_tracker = HabitTracker()
