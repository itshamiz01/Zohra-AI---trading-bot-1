import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = "logs/zohra_trades_a.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# check tables
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables: {tables}")

for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"Table '{t}' has {count} rows")
    if t == 'equity_curve':
        rows = conn.execute("SELECT * FROM equity_curve ORDER BY rowid DESC LIMIT 15").fetchall()
        for r in rows:
            print(dict(r))
