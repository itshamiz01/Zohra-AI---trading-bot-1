"""Persistent capability controls and redacted execution history, not credentials."""
import json
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager


PROJECT = Path(__file__).resolve().parents[3]


def workspace_root():
    return Path(os.getenv("ZOHRA_ASSISTANT_WORKSPACE", str(PROJECT / "assistant_workspace")))


class CapabilityStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else workspace_root()

    def connect(self):
        absolute = self.root.absolute()
        for candidate in (absolute, *absolute.parents):
            if candidate.is_symlink() or candidate.is_junction():
                raise PermissionError("Capability storage cannot use links or junctions")
        absolute.mkdir(parents=True, exist_ok=True)
        target = absolute / "assistant-runtime.db"
        if target.is_symlink() or (target.exists() and target.stat().st_nlink > 1):
            raise PermissionError("Capability database cannot be a link")
        connection = sqlite3.connect(target, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS tool_controls(tool_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tool_events(id INTEGER PRIMARY KEY, session TEXT,
                tool_id TEXT NOT NULL, status TEXT NOT NULL, elapsed_ms REAL NOT NULL,
                error TEXT, verified INTEGER NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def controls(self):
        with self.session() as db:
            return {row["tool_id"]: bool(row["enabled"]) for row in db.execute("SELECT * FROM tool_controls")}

    def enabled(self, tool_id):
        with self.session() as db:
            row = db.execute("SELECT enabled FROM tool_controls WHERE tool_id=?", (tool_id,)).fetchone()
            return row is None or bool(row["enabled"])

    def record(self, session, tool_id, status, elapsed_ms=0, error=None, verified=False):
        from zohra.services.chat.assistant_tools import redact_data
        with self.session() as db:
            db.execute("INSERT INTO tool_events(session,tool_id,status,elapsed_ms,error,verified) VALUES(?,?,?,?,?,?)",
                (session, tool_id, status, elapsed_ms, json.dumps(redact_data(error)) if error else None, int(verified)))

    def history(self, session, limit=50):
        with self.session() as db:
            rows = db.execute("SELECT * FROM tool_events WHERE session=? ORDER BY id DESC LIMIT ?", (session, limit)).fetchall()
            return [{**dict(row), "error": json.loads(row["error"]) if row["error"] else None,
                     "verified": bool(row["verified"])} for row in rows]

    def latest(self):
        with self.session() as db:
            rows = db.execute("SELECT e.tool_id,e.status,e.elapsed_ms,e.verified,e.created FROM tool_events e JOIN (SELECT tool_id,MAX(id) AS last_id FROM tool_events GROUP BY tool_id) latest ON e.id=latest.last_id").fetchall()
            return {row["tool_id"]: {**dict(row), "verified": bool(row["verified"])} for row in rows}
