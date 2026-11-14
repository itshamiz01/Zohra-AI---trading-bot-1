"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — OS CENTRAL NERVOUS SYSTEM                  ║
║      Master Orchestrator, Model Router & Integrated Context Engine   ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os
import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple

from zohra.core.base_module import ZohraModule
from zohra.event_bus import event_bus
from zohra.config.settings import settings

logger = logging.getLogger("zohra.core.zohra_core")

class ZohraCore:
    """
    ZOHRA OS Core Intelligence Layer (Central Nervous System).
    Manages module lifecycle, context pipeline synthesis, model routing, and workflow triggers.
    """
    def __init__(self):
        self.modules: Dict[str, ZohraModule] = {}
        self.running = False
        self._lock = threading.RLock()
        self.theme = "zohra_dark"
        self.model_fallbacks = ["gemini", "groq", "openrouter", "local"]
        self.active_provider = "gemini"

    def register_module(self, module: ZohraModule) -> bool:
        """Register a new system module to ZOHRA OS."""
        with self._lock:
            if module.name in self.modules:
                logger.warning(f"Module {module.name} is already registered. Overwriting.")
            self.modules[module.name] = module
            logger.info(f"Registered module: {module.name}")
            return True

    def initialize(self) -> bool:
        """Initializes all registered modules safely, including scheduler, workflow, and health monitors."""
        logger.info("Initializing ZOHRA OS Core Intelligence Layer...")
        try:
            import json
            theme_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "theme_config.json")
            if os.path.exists(theme_file):
                with open(theme_file, "r") as f:
                    data = json.load(f)
                    self.theme = data.get("current_theme", "zohra_dark")
                    logger.info(f"Loaded active theme: {self.theme}")
        except Exception as e:
            logger.warning(f"Failed to load active theme configuration: {e}")
            self.theme = "zohra_dark"

        # Register scheduler, workflow engine, and health monitor
        from zohra.core.workflow_engine import workflow_engine
        from zohra.core.task_scheduler import task_scheduler
        from zohra.core.health_monitor import health_monitor
        self.register_module(workflow_engine)
        self.register_module(task_scheduler)
        self.register_module(health_monitor)

        self.running = True
        success = True
        
        with self._lock:
            for name, module in self.modules.items():
                if not module.enabled:
                    continue
                try:
                    logger.info(f"Initializing module: {name}")
                    if not module.initialize():
                        logger.error(f"Module {name} failed to initialize.")
                        success = False
                except Exception as e:
                    logger.error(f"Exception during module {name} initialization: {e}", exc_info=True)
                    success = False
        return success

    def shutdown(self) -> bool:
        """Gracefully shuts down all modules."""
        logger.warning("Shutting down ZOHRA OS Core...")
        self.running = False
        success = True
        
        with self._lock:
            for name, module in self.modules.items():
                try:
                    logger.info(f"Shutting down module: {name}")
                    if not module.shutdown():
                        logger.error(f"Module {name} failed clean shutdown.")
                        success = False
                except Exception as e:
                    logger.error(f"Exception during module {name} shutdown: {e}", exc_info=True)
                    success = False
        return success

    # ─── Context Engine ───────────────────────────────────────────────
    def build_execution_context(self, active_workspace: str = "dashboard") -> Dict[str, Any]:
        """Collect and bundle system state, open trades, workspace parameters, and CPU health."""
        from zohra.core.state_store import state_store
        from zohra.core.health_monitor import health_monitor
        
        health_info = {}
        try:
            health_info = health_monitor.scan_health()
        except Exception:
            pass

        # Build combined state
        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "active_workspace": active_workspace,
            "system_state": state_store.get_all(),
            "health_diagnostics": health_info,
            "loaded_modules": list(self.modules.keys()),
        }

    # ─── Model Router ─────────────────────────────────────────────────
    def select_model_provider(self) -> str:
        """Determines the highest-priority functional LLM provider with failover fallbacks."""
        if getattr(settings, "OPENROUTER_API_KEY", ""):
            self.active_provider = "openrouter"
        elif getattr(settings, "GROQ_API_KEY", ""):
            self.active_provider = "groq"
        else:
            self.active_provider = "local"
        return self.active_provider

    # ─── System Health ────────────────────────────────────────────────
    def get_system_health(self) -> Dict[str, Any]:
        """Collect health status from all modules."""
        health = {}
        with self._lock:
            for name, module in self.modules.items():
                try:
                    health[name] = module.get_status()
                except Exception as e:
                    health[name] = {"status": "CRASHED", "error": str(e)}
        return health

# Central singleton instance
zohra_core = ZohraCore()
