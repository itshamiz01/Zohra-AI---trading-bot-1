"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — HEALTH MONITOR                             ║
║      Diagnoses CPU, RAM, Latency & Connection Failovers              ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import logging
import os
import psutil
import time
from typing import Dict, Any, List
from zohra.core.base_module import ZohraModule
from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.core.health_monitor")

class HealthMonitor(ZohraModule):
    """
    Monitors process and host resource parameters (CPU, RAM, Database connectivity).
    Triggers alarms via event bus when parameters exceed standard thresholds.
    """
    def __init__(self):
        super().__init__("HealthMonitor")
        self.process = psutil.Process(os.getpid())
        self.alerts: List[Dict[str, Any]] = []

    def initialize(self) -> bool:
        logger.info("Initializing ZOHRA Health Monitor...")
        return True

    def shutdown(self) -> bool:
        logger.info("Shutting down ZOHRA Health Monitor...")
        self.alerts.clear()
        return True

    def scan_health(self) -> Dict[str, Any]:
        """Perform host and process state diagnostics."""
        cpu_pct = psutil.cpu_percent(interval=None)
        process_cpu = self.process.cpu_percent(interval=None)
        
        mem = psutil.virtual_memory()
        process_mem = self.process.memory_info().rss / (1024 * 1024)  # MB

        db_ok = self._check_db_connectivity()
        mt5_ok = self._check_mt5_connectivity()

        # Build status payload
        status = {
            "host_cpu_pct": cpu_pct,
            "process_cpu_pct": process_cpu,
            "host_ram_used_pct": mem.percent,
            "process_ram_mb": round(process_mem, 1),
            "db_connected": db_ok,
            "mt5_connected": mt5_ok,
            "timestamp": time.time()
        }

        # Validate thresholds
        if cpu_pct > 90.0:
            self._log_alert("CRITICAL", f"High Host CPU usage: {cpu_pct}%")
        if mem.percent > 90.0:
            self._log_alert("CRITICAL", f"High Host RAM usage: {mem.percent}%")
        if not db_ok:
            self._log_alert("ERROR", "Database connection lost or suspended")
        if not mt5_ok:
            self._log_alert("ERROR", "MT5 Terminal connection link inactive")

        return status

    def _check_db_connectivity(self) -> bool:
        try:
            from zohra.db.connection import get_db
            with get_db() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _check_mt5_connectivity(self) -> bool:
        try:
            from zohra.brokers.manager import broker_manager as mt5_broker
            return mt5_broker.is_connected()
        except Exception:
            return False

    def _log_alert(self, level: str, message: str):
        alert = {
            "level": level,
            "message": message,
            "time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }
        # Keep list size bounded
        if len(self.alerts) > 20:
            self.alerts.pop(0)
        
        # Prevent spamming duplicate messages
        if not any(a["message"] == message for a in self.alerts[-3:]):
            self.alerts.append(alert)
            logger.warning(f"Health Alert [{level}]: {message}")
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(event_bus.publish("health_warning", alert))
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        info = super().get_status()
        diag = self.scan_health()
        info.update({
            "diagnostics": diag,
            "alerts": self.alerts,
            "overall_status": "CRITICAL" if any(a["level"] == "CRITICAL" for a in self.alerts) else "HEALTHY"
        })
        return info

health_monitor = HealthMonitor()
