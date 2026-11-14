"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — TASK SCHEDULER                             ║
║      Cron-like Background Trigger Engine & Delayed Action Runner     ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import logging
import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from zohra.core.base_module import ZohraModule

logger = logging.getLogger("zohra.core.task_scheduler")

class ScheduledJob:
    def __init__(
        self,
        job_id: str,
        name: str,
        handler: Callable[..., Any],
        args: Optional[Dict[str, Any]] = None,
        interval_seconds: Optional[int] = None,
        run_at: Optional[datetime] = None,
    ):
        self.job_id = job_id
        self.name = name
        self.handler = handler
        self.args = args or {}
        self.interval_seconds = interval_seconds
        self.run_at = run_at
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self._calculate_next_run()

    def _calculate_next_run(self):
        now = datetime.utcnow()
        if self.run_at:
            if self.run_at > now:
                self.next_run = self.run_at
            else:
                self.next_run = None
        elif self.interval_seconds:
            self.next_run = now + timedelta(seconds=self.interval_seconds)

class TaskScheduler(ZohraModule):
    """
    Background worker daemon trigger scheduled recurring and delayed jobs.
    """
    def __init__(self):
        super().__init__("TaskScheduler")
        self.jobs: Dict[str, ScheduledJob] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._running = False

    def initialize(self) -> bool:
        logger.info("Initializing ZOHRA Task Scheduler...")
        self._running = True
        # Run background schedule loop
        try:
            loop = asyncio.get_running_loop()
            self._loop_task = loop.create_task(self._schedule_loop())
        except RuntimeError:
            # Fallback if no running loop
            t = threading.Thread(target=self._start_standalone_loop, daemon=True)
            t.start()
        return True

    def shutdown(self) -> bool:
        logger.info("Shutting down ZOHRA Task Scheduler...")
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
        self.jobs.clear()
        return True

    def _start_standalone_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop_task = loop.create_task(self._schedule_loop())
        loop.run_forever()

    async def _schedule_loop(self):
        while self._running:
            try:
                now = datetime.utcnow()
                jobs_to_run = []
                for job in self.jobs.values():
                    if job.next_run and now >= job.next_run:
                        jobs_to_run.append(job)

                for job in jobs_to_run:
                    logger.info(f"Triggering scheduled job: {job.name} ({job.job_id})")
                    try:
                        if asyncio.iscoroutinefunction(job.handler):
                            await job.handler(**job.args)
                        else:
                            job.handler(**job.args)
                    except Exception as e:
                        logger.error(f"Error executing scheduled job {job.job_id}: {e}", exc_info=True)
                    
                    job.last_run = now
                    job._calculate_next_run()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(1.0)

    def schedule_recurring(self, job_id: str, name: str, interval_seconds: int, handler: Callable[..., Any], args: Optional[Dict[str, Any]] = None):
        job = ScheduledJob(job_id, name, handler, args, interval_seconds=interval_seconds)
        self.jobs[job_id] = job
        logger.info(f"Scheduled recurring job '{name}' every {interval_seconds}s.")

    def schedule_once(self, job_id: str, name: str, run_at: datetime, handler: Callable[..., Any], args: Optional[Dict[str, Any]] = None):
        job = ScheduledJob(job_id, name, handler, args, run_at=run_at)
        self.jobs[job_id] = job
        logger.info(f"Scheduled one-off job '{name}' to run at {run_at.isoformat()} UTC.")

    def cancel_job(self, job_id: str) -> bool:
        if job_id in self.jobs:
            del self.jobs[job_id]
            logger.info(f"Cancelled job '{job_id}'")
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        status_info = super().get_status()
        status_info.update({
            "jobs_count": len(self.jobs),
            "jobs": [
                {
                    "job_id": j.job_id,
                    "name": j.name,
                    "next_run": j.next_run.isoformat() if j.next_run else None,
                    "last_run": j.last_run.isoformat() if j.last_run else None,
                }
                for j in self.jobs.values()
            ]
        })
        return status_info

task_scheduler = TaskScheduler()
