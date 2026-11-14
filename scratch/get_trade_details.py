import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for db_name in ["logs/zohra_trades_a.db", "logs/zohra_trades.db", "logs/trades.db"]:
    if not os.path.exists(db_name):
        continue
    print(f"\n==================== DATABASE: {db_name} ====================")
    try:
        conn = sqlite3.connect(db_name)
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"Tables found: {tables}")
        for t in ["trades", "trade_rejections", "rejected_trades"]:
            if t in tables:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cursor.fetchone()[0]
                print(f"Table '{t}' has {cnt} rows.")
                if cnt > 0:
                    print(f"Sample / recent rows from '{t}':")
                    cursor.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 10")
                    rows = cursor.fetchall()
                    for r in rows:
                        d = dict(r)
                        # print selected fields to keep it clean
                        clean_d = {k: d[k] for k in d if d[k] is not None}
                        print(f"  {clean_d}")
        conn.close()
    except Exception as e:
        print(f"Error querying {db_name}: {e}")
