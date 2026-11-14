import sqlite3
import sys
import json
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# Last 3 days: June 22, 23, 24, 25 2026
cutoff = '2026-06-22'

def query_db(db_path, label):
    print(f"\n{'='*60}")
    print(f"DATABASE: {label} ({db_path})")
    print('='*60)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Schema
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"Tables: {[t[0] for t in tables]}")

        for tname in [t[0] for t in tables]:
            cols = conn.execute(f"PRAGMA table_info({tname})").fetchall()
            col_names = [c[1] for c in cols]
            print(f"\nTable '{tname}' columns: {col_names}")

            # Row count
            total = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
            print(f"Total rows: {total}")

            # Date range
            for date_col in ['timestamp_open', 'timestamp', 'open_time', 'created_at', 'time']:
                if date_col in col_names:
                    try:
                        mn = conn.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM {tname}").fetchone()
                        print(f"Date range ({date_col}): {mn[0]} -> {mn[1]}")
                        break
                    except:
                        pass

        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")

# Check all DBs
for db_info in [
    ('logs/zohra_trades.db', 'zohra_trades (main)'),
    ('logs/zohra_trades_a.db', 'zohra_trades_a (agent)'),
    ('logs/trades.db', 'trades'),
    ('logs/zohra.db', 'zohra'),
    ('logs/hie_data.db', 'hie_data'),
]:
    query_db(*db_info)
