import sqlite3
import pandas as pd

conn = sqlite3.connect("logs/zohra_trades_a.db")
df = pd.read_sql_query("SELECT * FROM trades", conn)
print(df)
conn.close()
