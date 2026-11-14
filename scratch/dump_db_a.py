import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('logs/zohra_trades_a.db')
conn.row_factory = sqlite3.Row

# Let's write the entire database dump of trades and evolution history to a file so we can view it
with open('scratch/db_a_dump.txt', 'w', encoding='utf-8') as f:
    f.write("=== ALL EVOLUTION HISTORY ===\n")
    rows = conn.execute("SELECT * FROM evolution_history ORDER BY id ASC").fetchall()
    for r in rows:
        f.write(f"ID: {r['id']} | Time: {r['timestamp']} | Run ID: {r['run_id']}\n")
        f.write(f"Summary: {r['summary']}\n")
        f.write(f"Adjustments: {r['adjustments_json']}\n")
        f.write(f"Recommendations: {r['recommendations_json']}\n")
        f.write("-" * 80 + "\n")

    f.write("\n=== ALL TRADES ===\n")
    trades = conn.execute("SELECT * FROM trades ORDER BY id ASC").fetchall()
    for t in trades:
        td = dict(t)
        f.write(f"Trade ID: {td['id']}\n")
        for k, v in td.items():
            if k != 'metadata':
                f.write(f"  {k}: {v}\n")
        if td.get('metadata'):
            f.write(f"  metadata: {td['metadata']}\n")
        f.write("-" * 50 + "\n")

print("Dump completed.")
conn.close()
