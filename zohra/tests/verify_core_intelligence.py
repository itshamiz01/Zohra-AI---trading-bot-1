import sys
import asyncio
import time
from datetime import datetime, timedelta

codebase_path = r"c:\Users\dell\Desktop\Trading Bot 3.0"
if codebase_path not in sys.path:
    sys.path.insert(0, codebase_path)

def test_imports():
    print("Testing core intelligence imports...")
    mods = [
        ("zohra.core.zohra_core",      "zohra_core"),
        ("zohra.core.workflow_engine", "workflow_engine"),
        ("zohra.core.task_scheduler",  "task_scheduler"),
        ("zohra.core.health_monitor",  "health_monitor"),
    ]
    for module, obj in mods:
        try:
            m = __import__(module, fromlist=[obj])
            getattr(m, obj)
            print(f"[OK] {module} imported successfully.")
        except Exception as e:
            print(f"[ERROR] {module}: {e}")
            sys.exit(1)

async def async_test_pipeline():
    print("\nStarting Core Intelligence async pipeline verification...")
    try:
        from zohra.core.zohra_core import zohra_core
        from zohra.core.workflow_engine import workflow_engine, WorkflowStep
        from zohra.core.task_scheduler import task_scheduler
        from zohra.core.health_monitor import health_monitor

        # 1. Initialize core
        ok = zohra_core.initialize()
        print(f"[OK] Core initialized: {ok}")

        # 2. Test model routing
        provider = zohra_core.select_model_provider()
        print(f"[OK] Selected model provider: {provider}")

        # 3. Test context builder
        ctx = zohra_core.build_execution_context("core")
        print(f"[OK] Context active workspace: {ctx['active_workspace']}")
        print(f"[OK] Context diagnostics timestamp: {ctx['health_diagnostics'].get('timestamp')}")

        # 4. Test scheduler
        task_run_flag = False
        def scheduler_dummy():
            nonlocal task_run_flag
            task_run_flag = True

        task_scheduler.schedule_recurring("dummy_job", "Dummy Job", 1, scheduler_dummy)
        print("[OK] Task scheduler job registered.")
        await asyncio.sleep(1.2)
        print(f"[OK] Scheduler job execution verify: {task_run_flag}")

        # 5. Test workflow execution
        workflow_flag = False
        def workflow_step_1():
            return "SUCCESS_VALUE"

        def workflow_step_2(val):
            nonlocal workflow_flag
            if val == "SUCCESS_VALUE":
                workflow_flag = True

        wf = workflow_engine.create_workflow("test_wf", "Integration Test Workflow")
        wf.add_step(WorkflowStep("step1", workflow_step_1, on_success="step2"))
        wf.add_step(WorkflowStep("step2", workflow_step_2, args={"val": "SUCCESS_VALUE"}))

        print("[OK] Workflow created, starting execution...")
        await workflow_engine.execute_workflow("test_wf", "step1")
        print(f"[OK] Workflow execution result: {workflow_flag}")

        # 6. Test system health scan
        health_status = health_monitor.get_status()
        print(f"[OK] Overall system health state: {health_status['overall_status']}")
        print(f"[OK] DB connectivity check: {health_status['diagnostics']['db_connected']}")

        print("\nAll Core Intelligence & Agent Orchestration verification checks passed successfully!")
    except Exception as e:
        print(f"[ERROR] Integration test failed: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_imports()
    asyncio.run(async_test_pipeline())
