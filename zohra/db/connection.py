"""
Database connection factory — PostgreSQL preferred, SQLite fallback.
"""

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Union

from zohra.config.settings import settings

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False


class DatabaseConnection:
    """Unified database access layer."""

    def __init__(self, url: Optional[str] = None, sqlite_path: Optional[str] = None):
        self.url = url or settings.database.url
        self.sqlite_path = sqlite_path or settings.database.sqlite_path
        self._backend = "postgresql" if self._is_postgres() else "sqlite"
        self._conn: Optional[Union[sqlite3.Connection, Any]] = None

    def _is_postgres(self) -> bool:
        return bool(self.url and self.url.startswith("postgresql") and PSYCOPG2_AVAILABLE)

    @property
    def backend(self) -> str:
        return self._backend

    def connect(self):
        if self._conn is not None:
            return self._conn

        if self._backend == "postgresql":
            self._conn = psycopg2.connect(self.url)
            self._conn.autocommit = False
        else:
            Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.sqlite_path, timeout=30.0, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            try:
                self._conn.execute("PRAGMA journal_mode=WAL;")
                self._conn.execute("PRAGMA synchronous=NORMAL;")
            except Exception as e:
                pass

        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def cursor(self) -> Generator:
        conn = self.connect()
        if self._backend == "postgresql":
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def execute_script(self, sql: str):
        """Run DDL — adapts PostgreSQL schema to SQLite."""
        conn = self.connect()
        adapted = self._adapt_schema(sql)

        if self._backend == "sqlite":
            conn.executescript(adapted)
            conn.commit()
        else:
            with conn.cursor() as cur:
                for statement in self._split_statements(adapted):
                    if statement.strip():
                        cur.execute(statement)
            conn.commit()

    def _adapt_schema(self, sql: str) -> str:
        if self._backend == "postgresql":
            return sql
        adapted = sql
        adapted = re.sub(r"\bSERIAL\b", "INTEGER", adapted)
        adapted = re.sub(r"\bBIGINT\b", "INTEGER", adapted)
        adapted = re.sub(r"\bTIMESTAMPTZ\b", "TEXT", adapted)
        adapted = re.sub(r"\bBOOLEAN\b", "INTEGER", adapted)
        adapted = re.sub(r"DEFAULT CURRENT_TIMESTAMP", "DEFAULT (datetime('now'))", adapted)
        # SQLite: inline PRIMARY KEY for autoincrement
        adapted = adapted.replace(
            "id                  INTEGER PRIMARY KEY,",
            "id                  INTEGER PRIMARY KEY AUTOINCREMENT,",
        )
        for prefix in ["trades", "rejected_trades", "equity_curve", "signals",
                       "system_logs", "news_events", "broker_accounts", "agent_actions"]:
            adapted = adapted.replace(
                f"id                    INTEGER PRIMARY KEY,",
                f"id                    INTEGER PRIMARY KEY AUTOINCREMENT,",
            )
            adapted = adapted.replace(
                f"id            INTEGER PRIMARY KEY,",
                f"id            INTEGER PRIMARY KEY AUTOINCREMENT,",
            )
            adapted = adapted.replace(
                f"id          INTEGER PRIMARY KEY,",
                f"id          INTEGER PRIMARY KEY AUTOINCREMENT,",
            )
            adapted = adapted.replace(
                f"id              INTEGER PRIMARY KEY,",
                f"id              INTEGER PRIMARY KEY AUTOINCREMENT,",
            )
        # Remove CHECK constraints that SQLite may not need
        adapted = re.sub(
            r"CHECK \(direction IN \('LONG', 'SHORT'\)\)",
            "",
            adapted,
        )
        return adapted

    @staticmethod
    def _split_statements(sql: str) -> list:
        parts = []
        current = []
        for line in sql.split("\n"):
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            current.append(line)
            if stripped.endswith(";"):
                parts.append("\n".join(current))
                current = []
        if current:
            parts.append("\n".join(current))
        return parts

    def placeholder(self) -> str:
        return "%s" if self._backend == "postgresql" else "?"


_schema_path = Path(__file__).parent / "schema.sql"
_db_instance: Optional[DatabaseConnection] = None


def get_db() -> DatabaseConnection:
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseConnection()
        _db_instance.connect()
        _db_instance.execute_script(_schema_path.read_text(encoding="utf-8"))
    return _db_instance
