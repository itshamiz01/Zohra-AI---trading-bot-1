import MetaTrader5 as mt5
from dotenv import load_dotenv
import os

load_dotenv()
login = int(os.getenv('MT5_LOGIN'))
password = os.getenv('MT5_PASSWORD')
server = os.getenv('MT5_SERVER')

print(f"Connecting to: Login={login}, Server={server}")

if mt5.initialize():
    if mt5.login(login, password=password, server=server):
        info = mt5.account_info()
        print(f"Account: {info.login} | Server: {info.server}")
        print(f"Balance: ${info.balance} | Equity: ${info.equity}")
        
        positions = mt5.positions_get()
        if positions:
            print(f"\nOpen Positions: {len(positions)}")
            for p in positions:
                direction = "BUY" if p.type == 0 else "SELL"
                print(f"  #{p.ticket} | {p.symbol} {direction} | {p.volume} lots | Profit: ${p.profit}")
        else:
            print("\n>>> NO OPEN POSITIONS ON MT5 <<<")
        
        # Check DB for stale positions
        import sqlite3
        conn = sqlite3.connect("logs/zohra_trades.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT trade_id, symbol, direction, entry_price, mt5_ticket FROM trades WHERE timestamp_close IS NULL")
        db_open = cursor.fetchall()
        if db_open:
            print(f"\nDB has {len(db_open)} 'open' trades (possibly stale):")
            for r in db_open:
                print(f"  DB#{r['trade_id']} | {r['symbol']} {r['direction']} | Ticket: {r['mt5_ticket']}")
        else:
            print("\nDB also shows no open trades.")
        conn.close()
    else:
        print(f"Login failed: {mt5.last_error()}")
    mt5.shutdown()
else:
    print(f"MT5 init failed: {mt5.last_error()}")
