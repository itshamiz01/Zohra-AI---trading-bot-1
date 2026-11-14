import sqlite3
import json

db_paths = ["logs/zohra_trades.db", "zohra/db/zohra_trades.db", "logs/trades.db"]
for path in db_paths:
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"Path: {path}, Tables: {tables}")
        for t in tables:
            rows = conn.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 3").fetchall()
            print(f"  Table {t} ({len(rows)} rows):")
            for r in rows:
                print(f"    {dict(r)}")
    except Exception as e:
        print(f"Error for {path}: {e}")
