import sqlite3
import pandas as pd

conn = sqlite3.connect("logs/zohra_trades.db")
df = pd.read_sql_query("SELECT id, timestamp, equity, balance, open_pnl, daily_pnl FROM equity_curve ORDER BY id ASC", conn)
pd.set_option('display.max_rows', 100)
print(df)
conn.close()
