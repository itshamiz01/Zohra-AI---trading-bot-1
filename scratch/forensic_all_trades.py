import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ============================================================
# FULL ANALYSIS: zohra_trades.db (ALL 161 trades)
# ============================================================
conn = sqlite3.connect('logs/zohra_trades.db')
conn.row_factory = sqlite3.Row

all_trades = conn.execute("SELECT * FROM trades ORDER BY id ASC").fetchall()
all_d = [dict(r) for r in all_trades]

# Get all columns
cols_check = conn.execute("PRAGMA table_info(trades)").fetchall()
col_names = [c[1] for c in cols_check]

print(f"Total trades in zohra_trades.db: {len(all_d)}")
print()

# Print every trade briefly
print(f"{'ID':<5} {'Open':<22} {'Close':<22} {'Sym':<10} {'Dir':<6} {'PnL':>8} {'Status':<8} {'Strat':<30} {'ExitCode'}")
print("-"*140)
for r in all_d:
    pnl = float(r.get('pnl_usd') or 0)
    print(f"{r.get('id',''):<5} {str(r.get('timestamp_open',''))[:21]:<22} {str(r.get('timestamp_close',''))[:21]:<22} {str(r.get('symbol','')):<10} {str(r.get('direction','')):<6} ${pnl:>7.2f} {str(r.get('status','')):<8} {str(r.get('strategy_used',''))[:29]:<30} {r.get('exit_reason_code','')}")

conn.close()
