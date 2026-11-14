import MetaTrader5 as mt5
from datetime import datetime, timedelta
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"c:\Users\dell\Desktop\trading_bot")

from zohra.config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TERMINAL_PATH

if not mt5.initialize(path=MT5_TERMINAL_PATH) if MT5_TERMINAL_PATH else mt5.initialize():
    if mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
        acc = mt5.account_info()
        print("=== MT5 CONNECTION DETAILS ===")
        print(f"Login  : {acc.login}")
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
    else:
        print("Login failed:", mt5.last_error())
    mt5.shutdown()
else:
    print("Init failed:", mt5.last_error())
