"""Read-only dashboard projections of persisted subsystem records."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from zohra.config import settings as config


def table_snapshot(path, table, limit=50, query=""):
    # Table names only come from the fixed lists below, never request parameters.
    path = Path(path).resolve()
    if not path.is_file():
        return {"status": "empty", "count": 0, "records": []}
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
            conn.row_factory = sqlite3.Row
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                return {"status": "empty", "count": 0, "records": []}
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            # Exclude embeddings and large binary/raw source payloads from the UI.
            columns = [c for c in columns if c not in {"embedding", "embedding_json", "raw_content", "audio_data", "image_data"}]
            names = ", ".join(f'"{c}"' for c in columns)
            where, params = "", []
            if query:
                where = " WHERE " + " OR ".join(f'CAST("{c}" AS TEXT) LIKE ? ESCAPE \'\\\'' for c in columns)
                term = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                params = [f"%{term}%"] * len(columns)
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"' + where, params).fetchone()[0]
            order = next((c for c in ("created_at", "timestamp", "id") if c in columns), columns[0])
            records = conn.execute(f'SELECT {names} FROM "{table}"{where} ORDER BY "{order}" DESC LIMIT ?', [*params, limit]).fetchall()
            return {"status": "ok", "count": count, "records": [dict(row) for row in records]}
    except sqlite3.Error:
        return {"status": "unavailable", "count": None, "records": []}


def research_snapshot():
    projects = table_snapshot(config.DB_PATH, "research_projects")
    sources = table_snapshot(config.DB_PATH, "research_sources")
    calendar = Path(config.__file__).parent / "economic_calendar.json"
    try:
        watchlist = json.loads(calendar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        watchlist = []
    return {"projects": projects, "sources": sources, "watchlist": watchlist,
            "calendar_status": "Configured watchlist; release dates not supplied"}


def memory_snapshot(query=""):
    groups = {}
    for table in ("episodic_memory", "semantic_memory", "procedural_memory", "cognitive_episodes", "decision_memory", "market_memory", "vector_chunks"):
        groups[table] = table_snapshot(config.DB_PATH, table, query=query)
    groups["hie_market_memory"] = table_snapshot(Path(config.LOG_DIR) / "hie_data.db", "hie_market_memory", query=query)
    return {"query": query, "search_mode": "text", "collections": groups,
            "total_memories": sum(item["count"] or 0 for item in groups.values())}


def learning_snapshot():
    groups = {table: table_snapshot(config.DB_PATH, table) for table in (
        "learning_lessons", "detected_mistakes", "mastery_levels", "learning_recommendations", "failure_patterns")}
    hie = Path(config.LOG_DIR) / "hie_data.db"
    groups["hie_setup_outcomes"] = table_snapshot(hie, "hie_setup_outcomes")
    groups["hie_pattern_stats"] = table_snapshot(hie, "hie_pattern_stats")
    return {"collections": groups}


def agent_snapshot():
    from zohra.core.zohra_core import zohra_core
    agents = []
    for name, state in zohra_core.get_system_health().items():
        agents.append({"id": name, "name": name.replace("_", " ").title(),
                       "role": "Registered module", "category": "CORE",
                       "status": str(state.get("status", "UNKNOWN")).upper()})
    return {"agents": agents, "total_agents": len(agents), "core_count": len(agents),
            "active_count": sum(a["status"] in {"ACTIVE", "RUNNING", "HEALTHY", "ONLINE"} for a in agents),
            "busy_count": sum(a["status"] == "BUSY" for a in agents),
            "offline_count": sum(a["status"] in {"OFFLINE", "STOPPED", "CRASHED", "DISABLED"} for a in agents),
            "status": "ok" if agents else "No modules registered in this API process"}


def timestamp():
    return datetime.now(timezone.utc).isoformat()
