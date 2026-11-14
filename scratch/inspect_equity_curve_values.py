import sqlite3
import pandas as pd

dbs = ["logs/zohra_trades_a.db", "logs/zohra_trades.db"]
for db in dbs:
    try:
        conn = sqlite3.connect(db)
        print(f"\n=== EQUITY CURVE VALUES FOR {db} ===")
        df = pd.read_sql_query("SELECT id, timestamp, equity, balance, open_pnl, daily_pnl FROM equity_curve ORDER BY id ASC", conn)
        print("First 3 rows:")
        print(df.head(3))
        print("Last 5 rows:")
        print(df.tail(5))
        conn.close()
    except Exception as e:
        print(f"Error for {db}: {e}")
