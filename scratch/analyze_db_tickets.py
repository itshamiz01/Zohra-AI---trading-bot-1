import sqlite3
import pandas as pd

# Load MT5 deals
df_mt5 = pd.read_csv("logs/mt5_full_deals.csv")
mt5_tickets = set(df_mt5['ticket'].dropna().unique())
mt5_orders = set(df_mt5['order'].dropna().unique())

print(f"Current MT5 has {len(mt5_tickets)} unique tickets and {len(mt5_orders)} unique orders.")

def check_db_tickets(db_name, path):
    try:
        conn = sqlite3.connect(path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if 'trades' in tables:
            df_trades = pd.read_sql_query("SELECT id, trade_id, mt5_ticket, symbol, direction, entry_price, pnl_usd, timestamp_open FROM trades", conn)
            print(f"\nDatabase: {db_name} (path: {path})")
            print(f"  Total trades in DB: {len(df_trades)}")
            
            db_tickets = df_trades['mt5_ticket'].dropna().unique()
            print(f"  Unique MT5 tickets in DB: {len(db_tickets)}")
            
            # Check overlap
            overlap = [t for t in db_tickets if t in mt5_tickets or str(t) in mt5_tickets]
            print(f"  Overlap with current MT5 tickets: {len(overlap)}")
            
            # If there's no overlap, show some tickets
            if len(db_tickets) > 0 and len(overlap) == 0:
                print("  Sample DB tickets:", list(db_tickets)[:10])
                print("  Sample MT5 tickets:", list(mt5_tickets)[:10])
                
            # Print first and last trade in DB
            if len(df_trades) > 0:
                df_sorted = df_trades.sort_values(by='timestamp_open')
                print(f"  First trade in DB: ID={df_sorted.iloc[0]['id']} | Symbol={df_sorted.iloc[0]['symbol']} | PnL={df_sorted.iloc[0]['pnl_usd']} | Time={df_sorted.iloc[0]['timestamp_open']}")
                print(f"  Last trade in DB: ID={df_sorted.iloc[-1]['id']} | Symbol={df_sorted.iloc[-1]['symbol']} | PnL={df_sorted.iloc[-1]['pnl_usd']} | Time={df_sorted.iloc[-1]['timestamp_open']}")
                
        conn.close()
    except Exception as e:
        print(f"Error for {db_name}: {e}")

check_db_tickets("zohra_trades_a.db", "logs/zohra_trades_a.db")
check_db_tickets("zohra_trades.db", "logs/zohra_trades.db")
check_db_tickets("trades.db", "logs/trades.db")
