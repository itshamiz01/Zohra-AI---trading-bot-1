import sqlite3
import sys
import os
from datetime import datetime, time
import MetaTrader5 as mt5

sys.stdout.reconfigure(encoding='utf-8')

# 1. Query databases
dbs = ['logs/zohra_trades.db', 'logs/zohra_trades_a.db', 'logs/trades.db', 'logs/zohra.db']
print("=== DB SEARCH FOR TODAY ===")
for db in dbs:
    if os.path.exists(db):
        try:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            # Print table structure or names
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for tbl in tables:
                # Count recent
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE timestamp_open >= '2026-06-25' OR open_time >= '2026-06-25' OR time >= '2026-06-25' OR timestamp >= '2026-06-25'").fetchone()[0]
                if cnt > 0:
                    print(f"Database: {db} | Table: {tbl} has {cnt} rows from today")
                    rows = conn.execute(f"SELECT * FROM {tbl} WHERE timestamp_open >= '2026-06-25' OR open_time >= '2026-06-25' OR time >= '2026-06-25' OR timestamp >= '2026-06-25' LIMIT 5").fetchall()
                    for r in rows:
                        print(f"  Row: {dict(r)}")
            conn.close()
        except Exception as e:
            print(f"Error querying {db}: {e}")

# 2. Query MT5 directly
print("\n=== MT5 DEALS TODAY ===")
from dotenv import load_dotenv
load_dotenv()
login = int(os.getenv("MT5_LOGIN"))
password = os.getenv("MT5_PASSWORD")
server = os.getenv("MT5_SERVER")

if not mt5.initialize():
    print("MT5 Init failed")
    sys.exit(1)

if not mt5.login(login, password, server):
    print("MT5 Login failed")
    mt5.shutdown()
    sys.exit(1)

# Query today's deals from midnight local/server time (or last 24h)
start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
deals = mt5.history_deals_get(start_time, datetime.now())
print(f"Deals since midnight ({start_time}): {len(deals) if deals else 0}")
if deals:
    import pandas as pd
    records = []
    for d in deals:
        records.append({
            "ticket": d.ticket,
            "position_id": d.position_id,
            "time": datetime.fromtimestamp(d.time),
            "symbol": d.symbol,
            "type": "BUY" if d.type == 0 else "SELL",
            "entry": "IN" if d.entry == 0 else "OUT",
            "volume": d.volume,
            "price": d.price,
            "profit": d.profit,
            "comment": d.comment
        })
    df = pd.DataFrame(records).sort_values("time")
    print(df.to_string())

mt5.shutdown()
