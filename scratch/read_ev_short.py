import sqlite3
conn = sqlite3.connect('logs/zohra_trades_a.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT id, timestamp, summary FROM evolution_history ORDER BY timestamp ASC').fetchall()
for r in rows:
    print(f"ID: {r['id']} | Time: {r['timestamp']}")
    print(f"Summary: {r['summary']}")
    print("-" * 80)
conn.close()
