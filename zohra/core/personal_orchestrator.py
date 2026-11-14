"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — PERSONAL ORCHESTRATOR                        ║
║      Daily Briefing, Priority Compilation & Recommendation Engine    ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import logging
from typing import Dict, Any, List
from zohra.core.personal_memory import personal_memory
from zohra.core.task_manager import task_manager
from zohra.core.goal_manager import goal_manager
from zohra.core.habit_tracker import habit_tracker

logger = logging.getLogger("zohra.personal.orchestrator")

class PersonalOrchestrator:
    """
    Compiles a daily morning briefing, surfaces at-risk habits,
    and generates proactive recommendations.
    """

    def generate_daily_briefing(self) -> Dict[str, Any]:
        logger.info("📅 Personal Orchestrator: Generating daily briefing...")

        pending_tasks  = task_manager.get_pending()
        goals          = goal_manager.get_all()
        habits         = habit_tracker.get_all()
        at_risk        = habit_tracker.get_at_risk()
        reminders      = personal_memory.get_reminders()

        high_priority  = [t for t in pending_tasks if t.get("priority") == "HIGH"]
        recommendations = self._build_recommendations(pending_tasks, at_risk, goals)

        return {
            "pending_tasks":     len(pending_tasks),
            "high_priority":     high_priority,
            "habits":            habits,
            "habits_at_risk":    at_risk,
            "active_goals":      goals,
            "upcoming_reminders": reminders[:5],
            "recommendations":   recommendations,
        }

    def _build_recommendations(
        self,
        pending_tasks: List[Dict],
        at_risk: List[Dict],
        goals: List[Dict],
    ) -> List[str]:
        recs: List[str] = []

        high = [t for t in pending_tasks if t.get("priority") == "HIGH"]
        if high:
            recs.append(f"You have {len(high)} HIGH-priority task(s). Start with '{high[0]['title']}'.")

        if at_risk:
            names = ", ".join(h["name"] for h in at_risk[:2])
            recs.append(f"Habit streak at risk: {names}. Schedule time today.")

        low_goals = [g for g in goals if g.get("progress_pct", 0) < 25]
        if low_goals:
            recs.append(f"Goal '{low_goals[0]['title']}' is under 25% complete. Consider adding sub-tasks.")

        if not recs:
            recs.append("Great work! Everything is on track. Keep the momentum going.")

        return recs

    def add_task(self, title: str, priority: str = "MEDIUM", due_at: str = "") -> Dict[str, Any]:
        result = task_manager.create(title, priority, due_at)
        try:
            from zohra.core.cognitive_memory import cognitive_memory
            cognitive_memory.add_timeline_event(
                event_type="TASK_CREATED",
                description=f"Created task: '{title}' [{priority}]",
                reference_id=str(result["task_id"])
            )
        except Exception as e:
            logger.error(f"Timeline log failed: {e}")
        return result

    def add_goal(self, title: str, category: str = "PERSONAL", due_at: str = "") -> Dict[str, Any]:
        result = goal_manager.create(title, category, due_at)
        try:
            from zohra.core.cognitive_memory import cognitive_memory
            cognitive_memory.add_timeline_event(
                event_type="GOAL_CREATED",
                description=f"Created goal: '{title}' [{category}]",
                reference_id=str(result["goal_id"])
            )
        except Exception as e:
            logger.error(f"Timeline log failed: {e}")
        return result

    def get_kpi_summary(self) -> Dict[str, Any]:
        pending = task_manager.get_pending()
        goals   = goal_manager.get_all()
        habits  = habit_tracker.get_all()
        top_streak = max((h["streak"] for h in habits), default=0)
        avg_goal   = sum(g["progress_pct"] for g in goals) / len(goals) if goals else 0.0
        return {
            "pending_tasks": len(pending),
            "active_goals":  len(goals),
            "top_streak":    top_streak,
            "avg_goal_pct":  round(avg_goal, 1),
        }

# Singleton
personal_orchestrator = PersonalOrchestrator()
