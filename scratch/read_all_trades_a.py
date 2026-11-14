import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('logs/zohra_trades_a.db')
conn.row_factory = sqlite3.Row

trades = conn.execute("SELECT * FROM trades ORDER BY id ASC").fetchall()
print(f"Total trades: {len(trades)}")
for t in trades:
    d = dict(t)
    print(f"ID: {d['id']} | Open: {d['timestamp_open']} | Close: {d['timestamp_close']} | Sym: {d['symbol']} | Dir: {d['direction']} | Entry: {d['entry_price']} | SL: {d['stop_loss']} | TP: {d['take_profit']} | Exit: {d['exit_price']} | PnL: {d['pnl_usd']} | Reason Exit: {d['reason_for_exit']} | Reason Entry: {d['reason_for_entry'][:80] if d['reason_for_entry'] else None}")

conn.close()
