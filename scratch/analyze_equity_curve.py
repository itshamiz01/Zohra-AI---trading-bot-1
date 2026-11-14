import sqlite3
import pandas as pd

dbs = ["logs/zohra_trades_a.db", "logs/zohra_trades.db", "logs/trades.db"]
for db in dbs:
    try:
        conn = sqlite3.connect(db)
        print(f"\n========================================\nEQUITY CURVE FOR: {db}\n========================================")
        df = pd.read_sql_query("SELECT * FROM equity_curve ORDER BY id ASC", conn)
        print(df)
        conn.close()
    except Exception as e:
        print(f"Error for {db}: {e}")
