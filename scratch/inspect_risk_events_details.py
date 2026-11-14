import sqlite3

conn = sqlite3.connect("logs/zohra_trades_a.db")

print("=== RISK EVENTS (First 50) ===")
rows = conn.execute("SELECT id, timestamp, event_type, description, action_taken FROM risk_events ORDER BY id ASC LIMIT 50").fetchall()
for r in rows:
    print(f"ID: {r[0]} | Time: {r[1]} | Type: {r[2]} | Desc: {r[3]} | Action: {r[4]}")

print("\n=== SYSTEM LOGS ===")
rows_logs = conn.execute("SELECT id, timestamp, level, module, message FROM system_logs ORDER BY id ASC LIMIT 100").fetchall()
for r in rows_logs:
    print(f"ID: {r[0]} | Time: {r[1]} | Lvl: {r[2]} | Mod: {r[3]} | Msg: {r[4]}")

conn.close()
