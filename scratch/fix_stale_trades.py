import MetaTrader5 as mt5
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
mt5.initialize()
mt5.login(int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER'))

conn = sqlite3.connect('logs/zohra_trades.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT trade_id, symbol, direction, mt5_ticket FROM trades WHERE timestamp_close IS NULL")
stale = cursor.fetchall()

print(f"Found {len(stale)} stale open trade(s) in DB")

for row in stale:
    ticket = row['mt5_ticket']
    symbol = row['symbol']
    # Check deal history for this ticket
    deals = mt5.history_deals_get(position=ticket)
    if deals and len(deals) >= 2:
        close_deal = deals[-1]
        pnl = close_deal.profit + close_deal.commission + close_deal.swap
        cursor.execute(
            "UPDATE trades SET timestamp_close=?, exit_price=?, pnl_usd=? WHERE mt5_ticket=? AND timestamp_close IS NULL",
            (datetime.utcnow().isoformat(), close_deal.price, round(pnl, 2), ticket)
        )
        print(f"  Fixed: {symbol} #{ticket} -> PnL=${pnl:.2f} | Exit: {close_deal.price}")
    else:
        print(f"  No deal history for {symbol} #{ticket}, marking closed with $0")
        cursor.execute(
            "UPDATE trades SET timestamp_close=?, pnl_usd=0.0 WHERE mt5_ticket=? AND timestamp_close IS NULL",
            (datetime.utcnow().isoformat(), ticket)
        )

conn.commit()
conn.close()
mt5.shutdown()
print("Done! Stale positions cleaned.")
