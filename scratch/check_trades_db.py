import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = "logs/zohra.db"
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables in {db_path}: {tables}")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"Table '{table}' has {count} rows")
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 10").fetchall()
        for r in rows:
            print(dict(r))
except Exception as e:
    print(f"Error checking {db_path}: {e}")
