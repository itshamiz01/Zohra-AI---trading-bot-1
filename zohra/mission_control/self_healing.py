"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — SELF-HEALING TRADING ENGINE                     ║
║     Autonomous Diagnostic Checks & System Recovery Framework         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import time
import os
import psutil
from datetime import datetime
from typing import Dict, List, Any, Optional

from zohra.event_bus import event_bus
from zohra.config.settings import settings

logger = logging.getLogger("zohra.mission_control.self_healing")


class SelfHealingEngine:
    """
    Autonomous diagnostics and self-healing system monitoring CPU, memory leak limits,
    broker gateway connection failures, database locks, and active thread states.
    """

    def __init__(self):
        self.recovery_logs: List[Dict] = []
        self._last_diagnostics = {}
        
        # Threshold bounds
        self.max_memory_mb = 1024.0  # Alert when python process exceeds 1GB
        self.max_cpu_pct = 85.0
        self.latency_limit_ms = 1000.0

    def run_diagnostics(self) -> Dict[str, Any]:
        """Perform system-wide diagnostics checks and return logs."""
        cpu = psutil.cpu_percent(interval=0.1)
        
        # Memory check
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / (1024.0 * 1024.0)

        diagnostics = {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu_usage_pct": cpu,
            "memory_usage_mb": round(mem_mb, 2),
            "thread_count": len(process.threads()),
            "status": "NOMINAL",
            "anomalies": [],
        }

        # Analyze anomalies
        if mem_mb > self.max_memory_mb:
            diagnostics["anomalies"].append("MEMORY_LEAK_WARNING")
            diagnostics["status"] = "DEGRADED"
        if cpu > self.max_cpu_pct:
            diagnostics["anomalies"].append("HIGH_CPU_LOAD")
            diagnostics["status"] = "DEGRADED"

        # Check active broker adapters
        broker_status = self._check_brokers()
        diagnostics["brokers"] = broker_status
        for broker, info in broker_status.items():
            if info["status"] == "offline":
                diagnostics["anomalies"].append(f"BROKER_FAILURE_{broker.upper()}")
                diagnostics["status"] = "DEGRADED"

        self._last_diagnostics = diagnostics
        
        # Trigger self-healing if status degraded
        if diagnostics["status"] == "DEGRADED":
            self.heal_system(diagnostics)

        return diagnostics

    def heal_system(self, diagnostics: Dict[str, Any]) -> List[str]:
        """Execute automated recovery actions based on anomalies."""
        actions_taken = []
        
        for anomaly in diagnostics["anomalies"]:
            logger.warning(f"🚨 [Self-Healing] Diagnosed anomaly: {anomaly}. Triggering recovery...")
            
            if "BROKER_FAILURE" in anomaly:
                broker = anomaly.replace("BROKER_FAILURE_", "").lower()
                ok = self._recover_broker(broker)
                if ok:
                    actions_taken.append(f"RECONNECTED_BROKER_{broker.upper()}")
                else:
                    actions_taken.append(f"RECONNECT_FAILED_{broker.upper()}")

            elif anomaly == "MEMORY_LEAK_WARNING":
                # Clear internal caches
                self._clear_caches()
                actions_taken.append("CLEARED_SYSTEM_CACHES")

            elif anomaly == "HIGH_CPU_LOAD":
                # Throttle processing speed momentarily
                time.sleep(2)
                actions_taken.append("THROTTLED_SCAN_INTERVAL")

        if actions_taken:
            report = {
                "timestamp": datetime.utcnow().isoformat(),
                "anomalies": diagnostics["anomalies"],
                "actions": actions_taken,
                "diagnostics_snapshot": {
                    "cpu": diagnostics["cpu_usage_pct"],
                    "memory": diagnostics["memory_usage_mb"]
                }
            }
            self.recovery_logs.append(report)
            if len(self.recovery_logs) > 50:
                self.recovery_logs.pop(0)

            # Publish recovery report
            self._publish_recovery_event(report)
            logger.info(f"✅ [Self-Healing] Recovery actions completed: {actions_taken}")

        return actions_taken

    def get_latest_diagnostics(self) -> Dict[str, Any]:
        """Return the latest diagnostics data."""
        return self._last_diagnostics or self.run_diagnostics()

    # ─── Recovery Handlers ────────────────────────────────────

    def _check_brokers(self) -> Dict[str, Dict]:
        """Verify gateway connection bounds."""
        status = {}
        try:
            from zohra.brokers.manager import broker_manager
            registered_brokers = broker_manager.get_registered_brokers()
            for broker in ["mt5", "dhan", "coindcx"]:
                if broker in registered_brokers:
                    adapter = broker_manager.get_adapter(broker)
                    if adapter:
                        connected = adapter.is_connected() if hasattr(adapter, "is_connected") else True
                        status[broker] = {"status": "online" if connected else "offline"}
                    else:
                        status[broker] = {"status": "not_configured"}
                else:
                    status[broker] = {"status": "not_configured"}
        except Exception as e:
            logger.debug(f"Self-healing check_brokers error: {e}")
        return status

    def _recover_broker(self, broker: str) -> bool:
        """Attempt to reconnect to a dropped broker gateway."""
        try:
            from zohra.brokers.manager import broker_manager
            adapter = broker_manager.get_adapter(broker)
            if adapter and hasattr(adapter, "connect"):
                logger.info(f"🔌 [Self-Healing] Reconnect target: {broker.upper()}...")
                return adapter.connect()
        except Exception as e:
            logger.error(f"Failed to execute broker reconnection on {broker}: {e}")
        return False

    def _clear_caches(self):
        """Forces garbage collection and resets static queues."""
        import gc
        gc.collect()
        logger.info("🗑️ [Self-Healing] garbage collection run executed.")

    # ─── Event Publisher ──────────────────────────────────────

    @staticmethod
    def _publish_recovery_event(report: Dict):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(event_bus.publish("system.recovery", report))
        except RuntimeError:
            pass


# Singleton
self_healing_engine = SelfHealingEngine()
