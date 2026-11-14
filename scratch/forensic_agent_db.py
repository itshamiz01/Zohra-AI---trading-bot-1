import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ============================================================
# FULL ANALYSIS: zohra_trades_a.db
# ============================================================
conn = sqlite3.connect('logs/zohra_trades_a.db')
conn.row_factory = sqlite3.Row

cols = conn.execute("PRAGMA table_info(trades)").fetchall()
col_names = [c[1] for c in cols]
print(f"zohra_trades_a columns: {col_names}")
print()

all_trades = conn.execute("SELECT * FROM trades ORDER BY id ASC").fetchall()
print(f"Total trades in zohra_trades_a.db: {len(all_trades)}")
print()

for r in all_trades:
    d = dict(r)
    pnl = float(d.get('pnl_usd') or 0)
    print(f"--- Trade ID: {d.get('id')} ---")
    for k, v in d.items():
        if k != 'metadata':
            print(f"  {k}: {v}")
    # metadata separately
    meta = d.get('metadata', '')
    if meta:
        print(f"  metadata (first 200): {str(meta)[:200]}")
    print()

# Decision journal from zohra_trades_a
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"All tables: {[t[0] for t in tables]}")
for tname in [t[0] for t in tables]:
    cnt = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
    if cnt > 0 and tname != 'trades':
        print(f"\nTable: {tname} ({cnt} rows) - sample:")
        rows = conn.execute(f"SELECT * FROM {tname} LIMIT 5").fetchall()
        for row in rows:
            print(f"  {dict(row)}")

conn.close()
