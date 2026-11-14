import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ============================================================
# QUERY 1: zohra_trades_a.db - MAIN ACTIVE DB
# ============================================================
print("=" * 70)
print("FORENSIC TRADE DUMP: logs/zohra_trades_a.db")
print("=" * 70)

conn = sqlite3.connect('logs/zohra_trades_a.db')
conn.row_factory = sqlite3.Row

# All trades
all_trades = conn.execute("""
    SELECT * FROM trades ORDER BY id ASC
""").fetchall()

print(f"Total ALL-TIME trades: {len(all_trades)}")

# Last 3 days: June 22, 23, 24, 25 2026
recent = conn.execute("""
    SELECT * FROM trades
    WHERE (timestamp_open >= '2026-06-22' OR timestamp_close >= '2026-06-22')
    ORDER BY id ASC
""").fetchall()

print(f"\nTotal LAST 3 DAYS trades (Jun 22-25): {len(recent)}")
print()

if recent:
    print(f"{'ID':<6} {'Open Time':<22} {'Sym':<10} {'Dir':<6} {'Lots':<6} {'Entry':<10} {'SL':<10} {'TP':<10} {'Exit':<10} {'PnL':>8} {'Status':<10} {'Exit Reason'}")
    print("-" * 140)
    for r in recent:
        d = dict(r)
        pnl = float(d.get('pnl_usd') or 0)
        print(f"{d.get('id',''):<6} {str(d.get('timestamp_open',''))[:21]:<22} {str(d.get('symbol','')):<10} {str(d.get('direction','')):<6} {str(d.get('position_size_lots','')):<6} {str(d.get('entry_price','')):<10} {str(d.get('stop_loss','')):<10} {str(d.get('take_profit','')):<10} {str(d.get('exit_price','')):<10} ${pnl:>7.2f} {str(d.get('status','')):<10} {str(d.get('reason_for_exit','') or d.get('exit_reason_code',''))}")

conn.close()

# ============================================================
# QUERY 2: zohra_trades.db (older / different DB)
# ============================================================
print("\n" + "=" * 70)
print("FORENSIC TRADE DUMP: logs/zohra_trades.db")
print("=" * 70)

conn2 = sqlite3.connect('logs/zohra_trades.db')
conn2.row_factory = sqlite3.Row

tables2 = conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"Tables: {[t[0] for t in tables2]}")

for tname in [t[0] for t in tables2]:
    cnt = conn2.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
    print(f"  {tname}: {cnt} rows")

# Check for recent trades
try:
    recent2 = conn2.execute("""
        SELECT * FROM trades
        WHERE (timestamp_open >= '2026-06-22' OR timestamp_close >= '2026-06-22' OR created_at >= '2026-06-22')
        ORDER BY id ASC
    """).fetchall()
    print(f"\nRecent trades (Jun 22-25): {len(recent2)}")
    for r in recent2:
        d = dict(r)
        pnl = float(d.get('pnl_usd') or 0)
        print(f"  ID: {d.get('id')} | {d.get('timestamp_open')} | {d.get('symbol')} | {d.get('direction')} | PnL: ${pnl:.2f} | {d.get('reason_for_exit') or d.get('exit_reason_code')}")
except Exception as e:
    print(f"Error: {e}")

conn2.close()
