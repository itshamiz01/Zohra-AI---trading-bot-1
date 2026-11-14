import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = "logs/zohra_trades_a.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Query row with ID 8
row = conn.execute("SELECT * FROM trades WHERE id=8").fetchone()
if row:
    d = dict(row)
    print("TRADE DETAIL FOR ID 8:")
    for k, v in d.items():
        if k == 'metadata' and v:
            print(f"  {k}:")
            try:
                meta = json.loads(v)
                for mk, mv in meta.items():
                    print(f"    {mk}: {mv}")
            except Exception:
                print(f"    {v}")
        else:
            print(f"  {k}: {v}")
else:
    print("Trade ID 8 not found")
