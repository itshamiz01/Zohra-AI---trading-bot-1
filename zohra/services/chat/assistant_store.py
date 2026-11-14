"""Assistant-owned conversation and tasks; never seeds demo records."""
import sqlite3
import json
from contextlib import closing
from pathlib import Path

from zohra.config import settings


class AssistantStore:
    def __init__(self, path=None):
        self.path = Path(path or Path(settings.LOG_DIR) / "assistant.db")

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, id);
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if "sources" not in {row[1] for row in conn.execute("PRAGMA table_info(messages)")}:
            try:
                conn.execute("ALTER TABLE messages ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'")
                conn.commit()
            except sqlite3.OperationalError:
                if "sources" not in {row[1] for row in conn.execute("PRAGMA table_info(messages)")}:
                    raise
        if "private_context" not in {row[1] for row in conn.execute("PRAGMA table_info(messages)")}:
            try:
                # Existing unclassified history is not safe to send to another provider.
                conn.execute("ALTER TABLE messages ADD COLUMN private_context INTEGER NOT NULL DEFAULT 1")
                conn.commit()
            except sqlite3.OperationalError:
                if "private_context" not in {row[1] for row in conn.execute("PRAGMA table_info(messages)")}:
                    raise
        return conn

    def history(self, session_id, include_sources=False, external_only=False):
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT role, content, sources FROM messages WHERE session_id=? " +
                                ("AND private_context=0 " if external_only else "") +
                                "ORDER BY id DESC LIMIT 20", (session_id,)).fetchall()
        return [{"role": row["role"], "content": row["content"],
                 **({"sources": json.loads(row["sources"])} if include_sources else {})}
                for row in reversed(rows)]

    def add_message(self, session_id, role, content, sources=None, private_context=False):
        with closing(self._connect()) as conn, conn:
            conn.execute("INSERT INTO messages(session_id,role,content,sources,private_context) VALUES(?,?,?,?,?)",
                         (session_id, role, content, json.dumps(sources or [], ensure_ascii=False), int(private_context)))

    def manage_tasks(self, action="list", title="", task_id=None):
        if action not in {"list", "create", "complete"}:
            return {"error": "Unknown task action."}
        if action == "create" and (not isinstance(title, str) or not title.strip() or len(title) > 500):
            return {"error": "A task title between 1 and 500 characters is required."}
        with closing(self._connect()) as conn, conn:
            if action == "create":
                cursor = conn.execute("INSERT INTO tasks(title) VALUES(?)", (title.strip(),))
                return {"status": "created", "task_id": cursor.lastrowid, "title": title.strip()}
            if action == "complete":
                if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1:
                    return {"error": "A valid task ID is required."}
                cursor = conn.execute("UPDATE tasks SET status='complete' WHERE id=? AND status='pending'", (task_id,))
                return {"status": "completed" if cursor.rowcount else "not_pending", "task_id": task_id}
            return {"tasks": [dict(row) for row in conn.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT 100")],
                "pending_count": conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]}


assistant_store = AssistantStore()
