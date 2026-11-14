"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — GOAL MANAGER                               ║
║       Long-Term Goal Tracking with Category & Progress Rings         ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import logging
from typing import List, Dict, Any
from zohra.core.personal_memory import personal_memory

logger = logging.getLogger("zohra.personal.goal")

CATEGORIES = ["FINANCIAL", "HEALTH", "LEARNING", "BUSINESS", "PERSONAL"]

class GoalManager:
    def create(self, title: str, category: str = "PERSONAL", due_at: str = "") -> Dict[str, Any]:
        cat = category.upper() if category.upper() in CATEGORIES else "PERSONAL"
        logger.info(f"🎯 Creating goal: '{title}' [{cat}]")
        goal_id = personal_memory.add_goal(title, cat, due_at)
        return {"goal_id": goal_id, "title": title, "category": cat, "progress_pct": 0.0}

    def update_progress(self, goal_id: int, progress_pct: float) -> bool:
        logger.info(f"📈 Updating goal #{goal_id} progress to {progress_pct}%")
        return personal_memory.update_goal_progress(goal_id, min(100.0, max(0.0, progress_pct)))

    def get_all(self) -> List[Dict[str, Any]]:
        return personal_memory.get_goals()

    def get_summary(self) -> Dict[str, Any]:
        goals = self.get_all()
        by_category: Dict[str, List] = {}
        for g in goals:
            cat = g.get("category", "PERSONAL")
            by_category.setdefault(cat, []).append(g)
        avg_progress = sum(g["progress_pct"] for g in goals) / len(goals) if goals else 0.0
        return {"goals": goals, "by_category": by_category, "avg_progress_pct": round(avg_progress, 1)}

goal_manager = GoalManager()
