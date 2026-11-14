import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = "logs/zohra_trades_a.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Query trades
print("TRADES TABLE SUMMARY FOR logs/zohra_trades.db:")
try:
    trades = conn.execute("SELECT * FROM trades ORDER BY rowid DESC").fetchall()
    print(f"Total trades in DB: {len(trades)}")
    for t in trades[:30]:
        d = dict(t)
        # remove metadata if it's too long
        if 'metadata' in d and d['metadata']:
            d['metadata'] = d['metadata'][:50] + "..." if len(str(d['metadata'])) > 50 else d['metadata']
        print(f"ID: {d.get('id')} | Sym: {d.get('symbol')} | Dir: {d.get('direction')} | Entry: {d.get('entry_price')} | SL: {d.get('stop_loss')} | TP: {d.get('take_profit')} | PnL: {d.get('pnl_usd')} | Status: {d.get('status')} | Time: {d.get('timestamp') or d.get('timestamp_open')}")
except Exception as e:
    print(f"Error querying trades: {e}")
