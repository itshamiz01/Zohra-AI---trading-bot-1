import sqlite3
import pandas as pd

conn = sqlite3.connect("logs/zohra_trades_a.db")
print("=== RISK EVENTS ===")
df_risk = pd.read_sql_query("SELECT * FROM risk_events ORDER BY id ASC LIMIT 50", conn)
print(df_risk.head(20))
print(df_risk.tail(20))

print("\n=== SYSTEM LOGS ===")
df_logs = pd.read_sql_query("SELECT * FROM system_logs ORDER BY id ASC LIMIT 50", conn)
print(df_logs)

conn.close()
