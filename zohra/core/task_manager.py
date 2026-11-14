"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — TASK MANAGER                               ║
║            Priority-Aware Task Lifecycle Intelligence                ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import logging
from typing import List, Dict, Any
from zohra.core.personal_memory import personal_memory

logger = logging.getLogger("zohra.personal.task")

class TaskManager:
    def create(self, title: str, priority: str = "MEDIUM", due_at: str = "") -> Dict[str, Any]:
        logger.info(f"📋 Creating task: '{title}' [{priority}]")
        task_id = personal_memory.add_task(title, priority, due_at)
        return {"task_id": task_id, "title": title, "priority": priority, "status": "PENDING"}

    def complete(self, task_id: int) -> bool:
        logger.info(f"✅ Completing task #{task_id}")
        return personal_memory.complete_task(task_id)

    def get_pending(self) -> List[Dict[str, Any]]:
        return personal_memory.get_tasks(status="PENDING")

    def get_all(self) -> List[Dict[str, Any]]:
        return personal_memory.get_tasks()

task_manager = TaskManager()
