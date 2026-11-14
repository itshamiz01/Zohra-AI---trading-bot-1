import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('logs/zohra_trades_a.db')
conn.row_factory = sqlite3.Row

print("=== EVOLUTION HISTORY ===")
rows = conn.execute("SELECT * FROM evolution_history ORDER BY timestamp ASC").fetchall()
for r in rows:
    print(f"ID: {r['id']} | Time: {r['timestamp']} | Run ID: {r['run_id']}")
    print(f"Summary: {r['summary']}")
    print(f"Adjustments: {r['adjustments_json']}")
    print(f"Recommendations: {r['recommendations_json']}")
    print("-" * 80)

print("\n=== ALL TRADES IN zohra_trades_a.db ===")
trades = conn.execute("SELECT * FROM trades ORDER BY id ASC").fetchall()
for t in trades:
    td = dict(t)
    # Exclude metadata to keep it clean
    meta = td.pop('metadata', None)
    print(td)
    if meta:
        print(f"  Metadata: {str(meta)[:200]}")
    print("-" * 50)

conn.close()
