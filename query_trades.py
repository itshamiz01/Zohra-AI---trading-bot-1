import sqlite3
import sys

# Reconfigure stdout to use utf-8 to avoid encoding errors in python print
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('logs/zohra_trades.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 15").fetchall()

print("RECENT TRADES:")
for r in rows:
    d = dict(r)
    # Print clean details without crashing on encoding
    print(f"ID: {d.get('id')} | TradeID: {d.get('trade_id')} | Symbol: {d.get('symbol')} | Direction: {d.get('direction')} | Entry: {d.get('entry_price')} | Exit: {d.get('exit_price')} | SL: {d.get('stop_loss')} | TP: {d.get('take_profit')} | Lot: {d.get('position_size_lots')} | PnL: ${d.get('pnl_usd')} | Reason: {d.get('reason_for_entry')} | ExitReason: {d.get('reason_for_exit')}")
