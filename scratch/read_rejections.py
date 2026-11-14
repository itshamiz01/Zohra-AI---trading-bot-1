import sqlite3
import datetime

db_path = "logs/zohra_trades.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM rejected_trades ORDER BY id DESC LIMIT 5").fetchall()

print("--- RECENT REJECTIONS ---")
for r in rows:
    print(f"Time: {r['timestamp']} | Symbol: {r['symbol']} | Direction: {r['direction']} | Score: {r['confidence_score']}")
    print(f"  Reason: {r['reason_for_rejection']}")
    print(f"  Failed: {r['failed_conditions']}")
    print("-" * 50)
conn.close()
