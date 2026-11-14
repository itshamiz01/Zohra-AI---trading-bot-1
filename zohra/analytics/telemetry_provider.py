"""Dashboard telemetry, with unavailable measurements kept explicit."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import psutil
from zohra.config.settings import ACCOUNT_CONFIGS, LOG_DIR, DAILY_PROFIT_TARGET
from zohra.analytics.workspace_data import research_snapshot, memory_snapshot, learning_snapshot, agent_snapshot, timestamp


def get_system_telemetry():
    mem = psutil.virtual_memory()
    return {"cpu_usage_pct": psutil.cpu_percent(interval=None), "ram_usage_pct": mem.percent,
            "ram_used_gb": round(mem.used / 1024**3, 1), "ram_total_gb": round(mem.total / 1024**3, 1),
            "disk_usage_pct": psutil.disk_usage('.').percent, "gpu_usage": "Unavailable", "timestamp": timestamp()}


def fleet_snapshots():
    try:
        value = json.loads((Path(LOG_DIR) / "fleet_state.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def get_trading_telemetry(account_filter="all"):
    snapshots = fleet_snapshots()
    accounts = []
    for cfg in ACCOUNT_CONFIGS:
        snap = snapshots.get(cfg.account_id, {})
        recorded = snap.get("timestamp") or snap.get("updated_at")
        status = "UNAVAILABLE"
        if snap:
            status = "SNAPSHOT"
            try:
                instant = datetime.fromtimestamp(float(recorded), timezone.utc) if isinstance(recorded, (float, int)) else datetime.fromisoformat(recorded.replace("Z", "+00:00"))
                if instant.tzinfo is None:
                    instant = instant.replace(tzinfo=timezone.utc)
                status = "STALE" if (datetime.now(timezone.utc) - instant).total_seconds() > 60 else snap.get("connection_status", "ONLINE")
            except (ValueError, TypeError, AttributeError):
                pass
        accounts.append({"account_id": cfg.account_id, "name": cfg.name, "status": status,
                         "equity": snap.get("equity"), "balance": snap.get("balance"),
                         "daily_pnl": snap.get("daily_pnl"), "open_positions": snap.get("open_positions", len(snap.get("positions", [])) if snap else None),
                         "recorded_at": recorded, "is_demo": "demo" in (cfg.server or "").lower(),
                         "masked_login": f"***{str(cfg.login)[-4:]}" if cfg.login else "Unavailable"})
    selected = accounts if account_filter == "all" else [a for a in accounts if a["account_id"] == account_filter]
    result = {}
    for key in ("equity", "balance", "daily_pnl", "open_positions"):
        values = [a[key] for a in selected]
        result[key] = round(sum(values), 2) if values and all(isinstance(v, (float, int)) for v in values) else None
    balance, pnl = result["balance"], result["daily_pnl"]
    result.update({"scope": "Fleet" if account_filter == "all" else account_filter, "account_id": account_filter,
                   "pnl_pct": round(pnl / balance * 100, 2) if balance and pnl is not None else None,
                   "accounts": accounts, "sparkline": [], "status": "UNAVAILABLE" if not selected or all(a["status"] == "UNAVAILABLE" for a in selected) else "STALE" if any(a["status"] == "STALE" for a in selected) else "SNAPSHOT",
                   "target_goal": DAILY_PROFIT_TARGET * len(selected), "timestamp": timestamp()})
    return result


def get_divisions_telemetry():
    research, memory, learning, agents = research_snapshot(), memory_snapshot(), learning_snapshot(), agent_snapshot()
    return {"research_division": {"active_research": research["projects"]["count"], "papers_analyzed_today": None,
                                  "stored_sources": research["sources"]["count"]},
            "memory_core": {"total_memories": memory["total_memories"], "long_term_retention_pct": None},
            "learning_division": {"model_accuracy_pct": None, "learning_progress_pct": None,
                                  "total_setups_evaluated": learning["collections"]["hie_setup_outcomes"]["count"]},
            "evolution_engine": {"current_version": "Z-OS 1.7.3", "evolution_progress_pct": None},
            "ai_agents": agents,
            "active_operations": [{"name": a["name"], "status": a["status"]} for a in agents["agents"]]}


def get_command_center_telemetry(account_filter="all"):
    return {"system_status": "API ONLINE", "system_health_pct": None,
            "execution_mode": os.getenv("TRADING_EXECUTION_MODE", "paper"),
            "system_performance": get_system_telemetry(), "trading_division": get_trading_telemetry(account_filter),
            **get_divisions_telemetry(), "timestamp": timestamp()}
