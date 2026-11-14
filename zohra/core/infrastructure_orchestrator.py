"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — INFRASTRUCTURE ORCHESTRATOR                     ║
║   Service Registry, Model Cost Ledger & Operational Health Hub       ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from zohra.core.base_module import ZohraModule
from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.core.infra_orchestrator")

# ── Model Cost Table (per 1,000 tokens) ──────────────────────────────
MODEL_COST_TABLE: Dict[str, Dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.00015, "output": 0.0006},
    "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
    "google/gemini-2.5-flash": {"input": 0.00015, "output": 0.0006},
}


class ServiceRecord:
    def __init__(self, service_id: str, name: str, description: str = ""):
        self.service_id = service_id
        self.name = name
        self.description = description
        self.status = "RUNNING"      # RUNNING / STOPPED / DEGRADED
        self.started_at: float = time.time()
        self.restart_count: int = 0
        self.last_checked: float = time.time()

    def to_dict(self) -> Dict[str, Any]:
        uptime_sec = int(time.time() - self.started_at)
        return {
            "service_id": self.service_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "uptime_seconds": uptime_sec,
            "restart_count": self.restart_count,
            "last_checked": datetime.utcfromtimestamp(self.last_checked).isoformat(),
        }


class ModelCostLedger:
    """Tracks cumulative token usage and estimated USD cost per model."""

    def __init__(self):
        self.ledger: Dict[str, Dict[str, Any]] = {}

    def record_usage(self, model: str, input_tokens: int, output_tokens: int):
        if model not in self.ledger:
            self.ledger[model] = {
                "model": model,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost_usd": 0.0,
                "calls": 0,
            }
        costs = MODEL_COST_TABLE.get(model, {"input": 0.001, "output": 0.002})
        cost = (input_tokens / 1000 * costs["input"]) + (output_tokens / 1000 * costs["output"])
        self.ledger[model]["total_input_tokens"] += input_tokens
        self.ledger[model]["total_output_tokens"] += output_tokens
        self.ledger[model]["total_cost_usd"] += cost
        self.ledger[model]["calls"] += 1

    def get_weekly_summary(self) -> List[Dict[str, Any]]:
        summary = []
        for entry in self.ledger.values():
            summary.append({
                **entry,
                "total_cost_usd": round(entry["total_cost_usd"], 6),
            })
        return sorted(summary, key=lambda x: x["total_cost_usd"], reverse=True)

    def get_total_cost(self) -> float:
        return round(sum(e["total_cost_usd"] for e in self.ledger.values()), 4)


class InfrastructureOrchestrator(ZohraModule):
    """
    Manages all ZOHRA services (registry, health, cost) and coordinates
    backup scheduling, disaster recovery, and model telemetry.
    """

    def __init__(self):
        super().__init__("InfrastructureOrchestrator")
        self.services: Dict[str, ServiceRecord] = {}
        self.cost_ledger = ModelCostLedger()
        self.deployment_history: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
        self._register_default_services()

    def _register_default_services(self):
        defaults = [
            ("api_gateway",       "API Gateway",         "FastAPI REST & WebSocket endpoints"),
            ("trading_core",      "Trading Core",        "MT5 broker loops and signal scanners"),
            ("research_engine",   "Research Engine",     "Web research, PDF reader, fact checker"),
            ("learning_engine",   "Learning Engine",     "Pattern detection and strategy evolution"),
            ("memory_engine",     "Memory Engine",       "Vector store, cognitive memory, knowledge graph"),
            ("business_services", "Business Services",   "CRM, email drafting, project manager"),
            ("social_services",   "Social Services",     "Content generation, scheduler, analytics"),
            ("personal_services", "Personal Services",   "Tasks, goals, habit tracking, reminders"),
            ("scheduler",         "Task Scheduler",      "Background cron job executor"),
            ("workflow_engine",   "Workflow Engine",     "Sequential multi-step process runner"),
            ("sqlite_db",         "SQLite Database",     "Primary data persistence layer"),
        ]
        for sid, name, desc in defaults:
            self.services[sid] = ServiceRecord(sid, name, desc)

    def initialize(self) -> bool:
        logger.info("Initializing ZOHRA Infrastructure Orchestrator...")
        return True

    def shutdown(self) -> bool:
        logger.info("Shutting down ZOHRA Infrastructure Orchestrator...")
        return True

    # ── Service Controls ──────────────────────────────────────────────
    def restart_service(self, service_id: str) -> Dict[str, Any]:
        svc = self.services.get(service_id)
        if not svc:
            return {"success": False, "error": f"Service '{service_id}' not found."}
        svc.status = "RUNNING"
        svc.started_at = time.time()
        svc.restart_count += 1
        logger.info(f"Service restarted: {svc.name}")
        self._raise_alert("INFO", f"Service '{svc.name}' restarted manually.")
        return {"success": True, "service": svc.to_dict()}

    def stop_service(self, service_id: str) -> Dict[str, Any]:
        svc = self.services.get(service_id)
        if not svc:
            return {"success": False, "error": f"Service '{service_id}' not found."}
        svc.status = "STOPPED"
        logger.warning(f"Service stopped: {svc.name}")
        self._raise_alert("WARNING", f"Service '{svc.name}' was stopped.")
        return {"success": True, "service": svc.to_dict()}

    def get_all_services(self) -> List[Dict[str, Any]]:
        for svc in self.services.values():
            svc.last_checked = time.time()
        return [svc.to_dict() for svc in self.services.values()]

    # ── Alerts ────────────────────────────────────────────────────────
    def _raise_alert(self, level: str, message: str):
        alert = {
            "level": level,
            "message": message,
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        if len(self.alerts) > 30:
            self.alerts.pop(0)
        self.alerts.append(alert)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(event_bus.publish("infrastructure_alert", alert))
        except Exception:
            pass

    # ── Model Cost Ledger ──────────────────────────────────────────────
    def record_model_usage(self, model: str, input_tokens: int, output_tokens: int):
        self.cost_ledger.record_usage(model, input_tokens, output_tokens)

    def get_cost_summary(self) -> Dict[str, Any]:
        return {
            "weekly_breakdown": self.cost_ledger.get_weekly_summary(),
            "total_cost_usd": self.cost_ledger.get_total_cost(),
        }

    # ── Deployment Log ────────────────────────────────────────────────
    def log_deployment(self, version: str, environment: str = "production", notes: str = "") -> Dict[str, Any]:
        record = {
            "version": version,
            "environment": environment,
            "notes": notes,
            "deployed_at": datetime.utcnow().isoformat(),
            "status": "SUCCESS",
        }
        self.deployment_history.append(record)
        logger.info(f"Deployment logged: v{version} → {environment}")
        return record

    def get_deployment_history(self) -> List[Dict[str, Any]]:
        return list(reversed(self.deployment_history[-20:]))

    # ── Full Health Report ────────────────────────────────────────────
    def generate_health_report(self) -> Dict[str, Any]:
        from zohra.core.health_monitor import health_monitor
        from zohra.core.backup_manager import backup_manager

        services = self.get_all_services()
        running = sum(1 for s in services if s["status"] == "RUNNING")
        stopped = sum(1 for s in services if s["status"] == "STOPPED")
        degraded = sum(1 for s in services if s["status"] == "DEGRADED")

        try:
            diagnostics = health_monitor.scan_health()
        except Exception:
            diagnostics = {}

        try:
            backup_stats = backup_manager.get_backup_stats()
        except Exception:
            backup_stats = {}

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "services_running": running,
            "services_stopped": stopped,
            "services_degraded": degraded,
            "services": services,
            "diagnostics": diagnostics,
            "backup_stats": backup_stats,
            "model_costs": self.get_cost_summary(),
            "alerts": self.alerts[-10:],
            "recent_deployments": self.get_deployment_history()[:3],
        }

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "registered_services": len(self.services),
            "alerts_count": len(self.alerts),
            "total_model_cost_usd": self.cost_ledger.get_total_cost(),
        })
        return status


infra_orchestrator = InfrastructureOrchestrator()
