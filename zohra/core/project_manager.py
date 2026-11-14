"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — PROJECT MANAGEMENT ENGINE                    ║
║         SaaS, Publishing, & Operations Workspace Manager            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
from typing import List, Dict, Any
from zohra.core.business_memory import business_memory

logger = logging.getLogger("zohra.business.project")

class ProjectManager:
    """
    Manages operational project workspaces, tracking task progress
    and key performance indicators (KPIs).
    """
    def get_project_status(self) -> List[Dict[str, Any]]:
        projects = business_memory.get_projects()
        result = []
        for p in projects:
            kpis = {}
            if p.get("kpis_json"):
                try:
                    kpis = json.loads(p["kpis_json"])
                except Exception:
                    pass
            result.append({
                "id": p["id"],
                "name": p["name"],
                "status": p["status"],
                "progress_pct": kpis.get("progress_pct", 0),
                "tasks_completed": kpis.get("tasks_completed", 0),
                "total_tasks": kpis.get("total_tasks", 0)
            })
        return result

    def update_kpi(self, project_id: str, tasks_completed: int, total_tasks: int) -> bool:
        progress = int((tasks_completed / total_tasks * 100.0)) if total_tasks > 0 else 0
        kpis = {
            "progress_pct": progress,
            "tasks_completed": tasks_completed,
            "total_tasks": total_tasks
        }
        
        # Get project name
        projects = business_memory.get_projects()
        proj = next((p for p in projects if p["id"] == project_id), None)
        name = proj["name"] if proj else project_id
        status = proj["status"] if proj else "ACTIVE"
        
        return business_memory.add_project(project_id, name, status, kpis)

# Singleton
project_manager = ProjectManager()
