import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('logs/zohra_trades.db')
conn.row_factory = sqlite3.Row

# Schema check
cols = conn.execute("PRAGMA table_info(trades)").fetchall()
col_names = [c[1] for c in cols]
print(f"Trades table columns: {col_names}")
print()

# Date range check
mn = conn.execute("SELECT MIN(timestamp_open), MAX(timestamp_open), MIN(timestamp_close), MAX(timestamp_close) FROM trades").fetchone()
print(f"Open range: {mn[0]} -> {mn[1]}")
print(f"Close range: {mn[2]} -> {mn[3]}")
print()

# ALL trades
all_trades = conn.execute("SELECT * FROM trades ORDER BY id ASC").fetchall()
print(f"Total trades: {len(all_trades)}")
print()

# Last 3 days
recent = conn.execute("""
    SELECT * FROM trades
    WHERE timestamp_open >= '2026-06-22'
    ORDER BY id ASC
""").fetchall()
print(f"Recent trades (>= Jun 22): {len(recent)}")
print()

# Print all recent trades in detail
for r in recent:
    d = dict(r)
    pnl = float(d.get('pnl_usd') or 0)
    print(f"--- Trade ID: {d.get('id')} ---")
    print(f"  Symbol    : {d.get('symbol')} | Dir: {d.get('direction')} | Lots: {d.get('position_size_lots')}")
    print(f"  Open      : {d.get('timestamp_open')}")
    print(f"  Close     : {d.get('timestamp_close')}")
    print(f"  Entry     : {d.get('entry_price')} | SL: {d.get('stop_loss')} | TP: {d.get('take_profit')} | Exit: {d.get('exit_price')}")
    print(f"  PnL       : ${pnl:.2f} | Risk USD: {d.get('risk_usd')} | R:R: {d.get('risk_reward_ratio')}")
    print(f"  Strategy  : {d.get('strategy')}")
    print(f"  Status    : {d.get('status')}")
    print(f"  Regime    : {d.get('market_regime')}")
    print(f"  Session   : {d.get('session')}")
    print(f"  Confidence: {d.get('confidence_score')}")
    print(f"  Entry Reason: {d.get('reason_for_entry')}")
    print(f"  Exit Reason : {d.get('reason_for_exit')}")
    print(f"  Broker    : {d.get('broker')} | MT5 Ticket: {d.get('mt5_ticket')}")
    print()

# Also get ALL trades for aggregate stats
print("\n" + "="*70)
print("ALL-TIME AGGREGATE STATS")
print("="*70)
all_d = [dict(r) for r in all_trades]
pnls = [float(r.get('pnl_usd') or 0) for r in all_d]
closed = [r for r in all_d if r.get('status') not in ('OPEN', 'open', None) or float(r.get('pnl_usd') or 0) != 0]
print(f"Total trades: {len(all_d)}")
print(f"Closed trades: {len(closed)}")

conn.close()
