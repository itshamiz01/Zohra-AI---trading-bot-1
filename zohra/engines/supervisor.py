"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — SUPERVISOR (Process Lifecycle Manager)            ║
║     Starts, monitors, and restarts all ZOHRA processes              ║
╚══════════════════════════════════════════════════════════════════════╝

The Supervisor is the operating system's process manager for ZOHRA.

It should:
  ✅ Start processes
  ✅ Stop processes
  ✅ Restart crashed processes
  ✅ Monitor heartbeats
  ✅ Detect unhealthy workers
  ✅ Prevent duplicate workers
  ✅ Maintain system state
  ✅ Handle graceful shutdown

It must NOT:
  ❌ Generate trading signals
  ❌ Calculate indicators
  ❌ Place orders
  ❌ Manage MT5 directly
  ❌ Make trading decisions

Process Architecture:
  ┌─────────────────┐
  │   SUPERVISOR    │
  │ Process Manager │
  └────────┬────────┘
           │
  ┌────────┴────────┬──────────────┬──────────────┐
  │                 │              │              │
  ▼                 ▼              ▼              ▼
  Market Data    Strategy      Risk Engine    Account Workers
  Service        Engine                       (1, 2, 3)
"""

import os
import sys
import signal
import logging
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from zohra.core.message_bus import message_bus, ZohraMessage, MessageTopic, KillSwitchLevel
from zohra.config.settings import ACTIVE_ACCOUNT_CONFIGS, ACCOUNT_CONFIGS, LOG_DIR

logger = logging.getLogger("zohra.supervisor")

# ─── Banner ─────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║          ZOHRA UNIFIED TRADING OPERATING SYSTEM                  ║
║          ─────────────────────────────────────────                ║
║                                                                  ║
║    Centralized Intelligence │ Isolated Execution                 ║
║    15 Strategies │ 3 MT5 Accounts │ 1 System                     ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""


class ProcessState:
    """Tracks the state of a managed process/task or OS subprocess."""

    def __init__(self, name: str, component: Any = None, is_subprocess: bool = False, config: Any = None):
        self.name = name
        self.component = component
        self.task: Optional[asyncio.Task] = None
        self.popen = None            # subprocess.Popen if is_subprocess=True
        self.is_subprocess = is_subprocess
        self.config = config
        self.status = "STOPPED"       # STOPPED, STARTING, HEALTHY, DEGRADED, CRASHED
        self.start_count = 0
        self.last_heartbeat = 0.0
        self.crash_count = 0

    @property
    def is_alive(self) -> bool:
        if self.is_subprocess:
            return self.popen is not None and self.popen.poll() is None
        return self.task is not None and not self.task.done()


class ZohraSupervisor:
    """
    ZOHRA Unified System Supervisor.

    Orchestrates the lifecycle of all processes:
      0. Supervisor (this)
      1. Market Data Service
      2. Strategy Engine
      3. Risk & Decision Engine
      4-6. Account Workers (one per MT5 account)
    """

    PROCESS_NAME = "zohra-supervisor"
    HEARTBEAT_TIMEOUT_SEC = 60.0   # Mark process unhealthy if no heartbeat for 60s
    MAX_CRASH_RESTARTS = 5

    def __init__(self, account_ids: List[str] = None):
        self._running = False
        self._start_time = 0.0
        self._processes: Dict[str, ProcessState] = {}
        self._account_ids = account_ids  # Optional: subset of accounts to activate

        # ─── Components (instantiated on start) ───
        self._market_data = None
        self._strategy_engine = None
        self._risk_engine = None
        self._account_workers: Dict[str, Any] = {}

        # Subscribe to heartbeats
        message_bus.subscribe(
            MessageTopic.SYSTEM_HEARTBEAT.value,
            self._on_heartbeat,
            subscriber_id="supervisor_heartbeat_monitor",
        )

        # Subscribe to account snapshots for live console reporting
        self._account_snapshots: Dict[str, Dict] = {}
        message_bus.subscribe(
            MessageTopic.ACCOUNT_SNAPSHOT.value,
            self._on_account_snapshot,
            subscriber_id="supervisor_account_monitor",
        )

        logger.info("ZohraSupervisor initialized")

    # ═══════════════════════════════════════════════════════════
    #  STARTUP
    # ═══════════════════════════════════════════════════════════

    async def start(self):
        """Start the entire ZOHRA unified system."""
        print(BANNER)
        self._start_time = time.time()
        self._running = True

        # Ensure log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)

        # ─── Print System Configuration ───
        self._print_system_config()

        # ─── 1. Start Market Data Service ───
        logger.info("━" * 60)
        logger.info("  Phase 1: Starting Market Data Service")
        logger.info("━" * 60)
        await self._start_market_data()

        # Wait for initial data cache to populate
        logger.info("⏳ Waiting for initial market data cache...")
        await asyncio.sleep(3.0)

        # ─── 2. Start Strategy Engine ───
        logger.info("━" * 60)
        logger.info("  Phase 2: Starting Strategy Engine (15 strategies)")
        logger.info("━" * 60)
        await self._start_strategy_engine()

        # ─── 3. Start Risk Engine ───
        logger.info("━" * 60)
        logger.info("  Phase 3: Starting Risk & Decision Engine")
        logger.info("━" * 60)
        await self._start_risk_engine()

        # ─── 4. Start Account Workers ───
        logger.info("━" * 60)
        logger.info("  Phase 4: Starting Account Workers")
        logger.info("━" * 60)
        await self._start_account_workers()

        # ─── 5. Start Web Command Center & 3D Dashboard ───
        logger.info("━" * 60)
        logger.info("  Phase 5: Starting Web Command Center & 3D Molecular Dashboard")
        logger.info("━" * 60)
        self._start_api_server()

        # ─── 6. Enter supervisor monitoring loop ───
        logger.info("━" * 60)
        logger.info("  ✅ All processes started — entering supervisor monitoring loop")
        logger.info("  🌐 Live Dashboard: http://127.0.0.1:8000")
        logger.info("  Press Ctrl+C to shut down gracefully")
        logger.info("━" * 60)
        await self._monitor_loop()

    async def _start_market_data(self):
        """Start the Market Data Service."""
        from zohra.engines.market_data_service import MarketDataService

        self._market_data = MarketDataService()
        if not self._market_data.start():
            logger.error("❌ Market Data Service failed to start — continuing with degraded mode")
            return

        ps = ProcessState("zohra-market-data", self._market_data)
        ps.task = asyncio.create_task(self._run_with_restart(ps, self._market_data.run_loop))
        ps.status = "HEALTHY"
        ps.start_count = 1
        self._processes[ps.name] = ps

    async def _start_strategy_engine(self):
        """Start the Unified Strategy Engine."""
        from zohra.engines.strategy_engine import UnifiedStrategyEngine

        self._strategy_engine = UnifiedStrategyEngine(market_data_service=self._market_data)
        self._strategy_engine.start()

        ps = ProcessState("zohra-strategy-engine", self._strategy_engine)
        ps.task = asyncio.create_task(self._run_with_restart(ps, self._strategy_engine.run_loop))
        ps.status = "HEALTHY"
        ps.start_count = 1
        self._processes[ps.name] = ps

    async def _start_risk_engine(self):
        """Start the Risk & Decision Engine."""
        from zohra.engines.risk_decision_engine import RiskDecisionEngine

        self._risk_engine = RiskDecisionEngine()
        self._risk_engine.start()

        ps = ProcessState("zohra-risk-engine", self._risk_engine)
        ps.task = asyncio.create_task(self._run_with_restart(ps, self._risk_engine.run_loop))
        ps.status = "HEALTHY"
        ps.start_count = 1
        self._processes[ps.name] = ps

    def _cleanup_existing_worker_processes(self):
        """Clean up any rogue/orphaned account worker processes from previous runs."""
        try:
            import psutil
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['pid'] == current_pid:
                        continue
                    cmdline = proc.info.get('cmdline') or []
                    cmd_str = " ".join(cmdline)
                    if "zohra.engines.account_worker" in cmd_str:
                        logger.info(f"🧹 Terminating orphaned worker process PID {proc.info['pid']}...")
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            logger.debug(f"Process cleanup check: {e}")

    def _start_api_server(self):
        """Start the unified web dashboard & API server in a background daemon thread."""
        try:
            import threading
            import uvicorn
            from zohra.api.app import app
            from zohra.config.settings import settings

            host = getattr(settings, "api_host", "127.0.0.1")
            port = int(getattr(settings, "api_port", 8000))

            def run():
                try:
                    uvicorn.run(app, host=host, port=port, log_level="warning")
                except Exception as ex:
                    logger.warning(f"Dashboard server error: {ex}")

            t = threading.Thread(target=run, daemon=True, name="zohra-dashboard-api")
            t.start()
            logger.info(f"  🌐 ZOHRA Dashboard & 3D Command Center live at: http://{host}:{port}")
        except Exception as e:
            logger.warning(f"Could not auto-start dashboard API: {e}")

    async def _start_account_workers(self):
        """Start Account Workers as isolated OS subprocesses (one per MT5 account)."""
        # First clean up any orphaned worker processes from previous runs
        self._cleanup_existing_worker_processes()

        configs = ACTIVE_ACCOUNT_CONFIGS
        if self._account_ids:
            configs = [c for c in ACCOUNT_CONFIGS
                       if c.account_id in self._account_ids or str(c.login) in self._account_ids]

        if not configs:
            logger.warning("⚠️ No active account configurations found! Check .env for MT5_ACCOUNT_*_LOGIN values.")
            return

        for config in configs:
            proc_name = f"zohra-account-{config.account_id}"
            ps = ProcessState(proc_name, component=None, is_subprocess=True, config=config)
            self._start_worker_subprocess(ps)
            self._processes[ps.name] = ps

    def _start_worker_subprocess(self, ps: ProcessState):
        """Launch an isolated worker subprocess with its own MT5 context and log file."""
        import subprocess
        config = ps.config
        cmd = [sys.executable, "-m", "zohra.engines.account_worker", "--account-id", config.account_id]
        log_path = os.path.join(LOG_DIR, f"worker_{config.account_id}.log")
        log_file = open(log_path, "a", encoding="utf-8")

        flags = 0
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags = subprocess.CREATE_NEW_PROCESS_GROUP

        popen = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=flags
        )
        ps.popen = popen
        ps.status = "HEALTHY"
        ps.start_count += 1
        logger.info(f"✅ Account Worker spawned [PID {popen.pid}]: {config.account_id} (Login: {config.login})")

    # ═══════════════════════════════════════════════════════════
    #  MONITORING LOOP
    # ═══════════════════════════════════════════════════════════

    async def _monitor_loop(self):
        """Main supervisor monitoring loop."""
        monitor_ticks = 0
        while self._running:
            try:
                monitor_ticks += 1
                # Check health of all processes
                for name, ps in list(self._processes.items()):
                    if ps.is_subprocess:
                        if ps.popen and ps.popen.poll() is not None:
                            retcode = ps.popen.poll()
                            ps.crash_count += 1
                            if ps.crash_count <= self.MAX_CRASH_RESTARTS:
                                logger.error(
                                    f"💀 Subprocess {name} exited with code {retcode} "
                                    f"(crash {ps.crash_count}/{self.MAX_CRASH_RESTARTS})"
                                )
                            if self._running and ps.crash_count < self.MAX_CRASH_RESTARTS:
                                ps.status = "RESTARTING"
                                logger.info(f"🔄 Restarting worker {name} in 5s...")
                                await asyncio.sleep(5.0)
                                self._start_worker_subprocess(ps)
                            else:
                                if ps.status != "FAILED":
                                    logger.critical(f"🛑 Worker {name} reached maximum restart limit ({self.MAX_CRASH_RESTARTS}).")
                                ps.status = "FAILED"
                                ps.popen = None
                    else:
                        if ps.task and ps.task.done():
                            exc = ps.task.exception() if not ps.task.cancelled() else None
                            if exc:
                                logger.error(f"💀 Process {name} crashed: {exc}")
                                ps.status = "CRASHED"
                                ps.crash_count += 1
                            else:
                                ps.status = "STOPPED"

                # Publish supervisor heartbeat
                await message_bus.publish_heartbeat(self.PROCESS_NAME, "HEALTHY", self.uptime)

                # Periodic live status dashboard in console every 30 seconds
                if monitor_ticks % 3 == 0:
                    import datetime
                    now_str = datetime.datetime.now().strftime("%H:%M:%S")
                    uptime_m = int(self.uptime // 60)
                    uptime_s = int(self.uptime % 60)
                    logger.info("═" * 68)
                    logger.info(f"  💓 [ZOHRA HEARTBEAT] {now_str} | Uptime: {uptime_m}m {uptime_s}s | System: HEALTHY")
                    for c in ACTIVE_ACCOUNT_CONFIGS:
                        snap = self._account_snapshots.get(c.account_id, {})
                        eq = snap.get("equity", 0.0)
                        pos = snap.get("open_positions", 0)
                        pnl = snap.get("daily_pnl", 0.0)
                        conn = "ONLINE" if c.account_id in self._account_snapshots else "CONNECTING"
                        logger.info(f"    • {c.name} (#{c.login}): Equity ${eq:,.2f} | Pos: {pos} | PnL: ${pnl:+.2f} | [{conn}]")
                    logger.info("═" * 68)

                # Status check interval
                await asyncio.sleep(10.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Supervisor monitor error: {e}")
                await asyncio.sleep(10.0)

    async def _run_with_restart(self, ps: ProcessState, coro_fn):
        """Run a coroutine with automatic restart on crash."""
        while self._running and ps.crash_count < self.MAX_CRASH_RESTARTS:
            try:
                await coro_fn()
            except asyncio.CancelledError:
                break
            except Exception as e:
                ps.crash_count += 1
                ps.status = "CRASHED"
                logger.error(
                    f"💀 Process {ps.name} crashed (attempt {ps.crash_count}/{self.MAX_CRASH_RESTARTS}): {e}",
                    exc_info=True
                )
                if ps.crash_count < self.MAX_CRASH_RESTARTS:
                    wait = min(30, 5 * ps.crash_count)
                    logger.info(f"🔄 Restarting {ps.name} in {wait}s...")
                    await asyncio.sleep(wait)
                    ps.status = "STARTING"
                    ps.start_count += 1
                else:
                    logger.critical(f"❌ Process {ps.name} exceeded max restarts — giving up")
                    ps.status = "DEAD"

    # ═══════════════════════════════════════════════════════════
    #  HEARTBEAT HANDLER
    # ═══════════════════════════════════════════════════════════

    async def _on_heartbeat(self, msg: ZohraMessage):
        """Track heartbeats from all processes."""
        process_name = msg.payload.get("process", "")
        if process_name in self._processes:
            self._processes[process_name].last_heartbeat = time.time()
            status = msg.payload.get("status", "UNKNOWN")
            if status != self._processes[process_name].status:
                self._processes[process_name].status = status

    async def _on_account_snapshot(self, msg: ZohraMessage):
        """Track live snapshots from account workers."""
        payload = msg.payload
        acct_id = payload.get("account_id")
        if acct_id:
            self._account_snapshots[acct_id] = payload
            try:
                import json
                fleet_file = os.path.join(LOG_DIR, "fleet_state.json")
                with open(fleet_file, "w", encoding="utf-8") as f:
                    json.dump(self._account_snapshots, f, default=str)
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════
    #  SHUTDOWN
    # ═══════════════════════════════════════════════════════════

    async def shutdown(self):
        """Gracefully shutdown all processes."""
        logger.info("🛑 Supervisor shutdown initiated...")
        self._running = False

        # Terminate all subprocess workers
        for name, ps in self._processes.items():
            if ps.is_subprocess and ps.popen and ps.popen.poll() is None:
                try:
                    logger.info(f"Terminating worker subprocess {name} [PID {ps.popen.pid}]...")
                    ps.popen.terminate()
                except Exception as e:
                    logger.warning(f"Error terminating {name}: {e}")

        # Stop in-memory engines
        if self._risk_engine:
            self._risk_engine.stop()
        if self._strategy_engine:
            self._strategy_engine.stop()
        if self._market_data:
            self._market_data.stop()

        # Cancel all async tasks
        for ps in self._processes.values():
            if ps.task and not ps.task.done():
                ps.task.cancel()

        # Shutdown message bus
        message_bus.shutdown()

        logger.info("✅ All processes stopped. ZOHRA shutdown complete.")

    # ═══════════════════════════════════════════════════════════
    #  KILL SWITCH
    # ═══════════════════════════════════════════════════════════

    async def kill_switch(self, level: str, target: str = None, reason: str = "Manual"):
        """Activate a kill switch."""
        await message_bus.publish_kill_switch(level, target, reason, self.PROCESS_NAME)

    # ═══════════════════════════════════════════════════════════
    #  DISPLAY HELPERS
    # ═══════════════════════════════════════════════════════════

    def _print_system_config(self):
        """Print system configuration at startup."""
        print("=" * 62)
        print("  ZOHRA UNIFIED SYSTEM CONFIGURATION")
        print("=" * 62)

        all_accounts = ACCOUNT_CONFIGS
        active = ACTIVE_ACCOUNT_CONFIGS

        print(f"  Total Accounts Configured: {len(all_accounts)}")
        print(f"  Active Accounts:           {len(active)}")
        print(f"  Strategies:                15 (all groups)")
        print()

        for i, config in enumerate(all_accounts, 1):
            status = "✅ ACTIVE" if config.enabled else "⚠️ INACTIVE (credentials needed)"
            print(f"  Account {i}: {config.name}")
            print(f"    Login:    {config.login}")
            print(f"    Server:   {config.server}")
            print(f"    Terminal: {config.terminal_path}")
            print(f"    Status:   {status}")
            print()

        print("=" * 62)

    def _print_startup_summary(self):
        """Print startup summary after all processes are running."""
        print()
        print("=" * 62)
        print("  ZOHRA STARTUP SUMMARY")
        print("=" * 62)

        for name, ps in self._processes.items():
            icon = "✅" if ps.status == "HEALTHY" else "❌"
            print(f"  {icon} {name:40s} [{ps.status}]")

        total = len(self._processes)
        healthy = sum(1 for ps in self._processes.values() if ps.status == "HEALTHY")
        print()
        print(f"  Processes: {healthy}/{total} healthy")
        print(f"  Account Workers: {len(self._account_workers)} active")
        print("=" * 62)
        print()

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    def get_system_status(self) -> Dict[str, Any]:
        """Get full system status."""
        return {
            "supervisor": {
                "status": "RUNNING" if self._running else "STOPPED",
                "uptime": self.uptime,
            },
            "processes": {
                name: {
                    "status": ps.status,
                    "start_count": ps.start_count,
                    "crash_count": ps.crash_count,
                    "alive": ps.is_alive,
                }
                for name, ps in self._processes.items()
            },
            "message_bus": message_bus.get_stats(),
        }
