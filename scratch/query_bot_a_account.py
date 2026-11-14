import MetaTrader5 as mt5
from datetime import datetime, timedelta
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

login = int(os.getenv("MT5_LOGIN"))
password = os.getenv("MT5_PASSWORD")
server = os.getenv("MT5_SERVER")

print("=== CONNECTING TO BOT A ACCOUNT ===")
print(f"Login: {login} | Server: {server}")

initialized = mt5.initialize()
if initialized:
    print("MT5 Initialized successfully.")
    logged_in = mt5.login(login, password, server)
    if logged_in:
        acc = mt5.account_info()
        print("=== SUCCESS ===")
        print(f"Account: {acc.login}")
        print(f"Server : {acc.server}")
        print(f"Balance: ${acc.balance:,.2f}")
        print(f"Equity : ${acc.equity:,.2f}")
        
        now = datetime.now()
        start_time = now - timedelta(days=4)
        
        deals = mt5.history_deals_get(start_time, now)
        print(f"\nDeals in history: {len(deals) if deals else 0}")
        if deals:
            for d in deals:
                print(f"  Deal: {d.ticket} | Time: {datetime.fromtimestamp(d.time)} | Symbol: {d.symbol} | Type: {d.type} | Vol: {d.volume} | Price: {d.price} | Profit: ${d.profit:+.2f} | Comment: {d.comment}")
                
        positions = mt5.positions_get()
        print(f"\nOpen Positions: {len(positions) if positions else 0}")
        if positions:
            for p in positions:
                print(f"  Pos: {p.ticket} | Symbol: {p.symbol} | Type: {p.type} | Vol: {p.volume} | Price Open: {p.price_open} | Profit: ${p.profit:+.2f}")
    else:
        print("Login failed:", mt5.last_error())
    mt5.shutdown()
else:
    print("Initialize failed:", mt5.last_error())
