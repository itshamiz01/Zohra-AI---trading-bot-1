import sqlite3
import datetime

db_path = "logs/zohra_trades.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM trades WHERE timestamp_open LIKE '2026-06-10%' ORDER BY id DESC").fetchall()

print(f"--- TRADES EXECUTED TODAY (June 10): {len(rows)} ---")
total_pnl = 0.0
for r in rows:
    pnl = float(r['pnl_usd'] or 0.0)
    total_pnl += pnl
    print(f"ID: {r['id']} | Time: {r['timestamp_open']} | Symbol: {r['symbol']} | Direction: {r['direction']} | Lots: {r['position_size_lots']}")
    print(f"  PnL: ${pnl:+.2f} | Strategy: {r['strategy_used']} | Exit Reason: {r['reason_for_exit']} ({r['exit_reason_code']})")
    print("-" * 60)
print(f"Total realized PnL today: ${total_pnl:+.2f}")
conn.close()
