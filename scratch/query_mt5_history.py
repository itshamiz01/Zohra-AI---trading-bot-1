import MetaTrader5 as mt5
from datetime import datetime, timedelta
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"c:\Users\dell\Desktop\trading_bot")

from zohra.config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TERMINAL_PATH

if not mt5.initialize(path=MT5_TERMINAL_PATH) if MT5_TERMINAL_PATH else mt5.initialize():
    print("MT5 initialized.")
    if mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
        print("Logged in successfully.")
        
        now = datetime.now()
        four_days_ago = now - timedelta(days=4)
        
        print(f"Querying history from {four_days_ago} to {now}")
        
        # Get history deals
        deals = mt5.history_deals_get(four_days_ago, now)
        if deals:
            print(f"Total deals found: {len(deals)}")
            for d in deals:
                print(f"Time: {datetime.fromtimestamp(d.time)} | Symbol: {d.symbol} | Type: {d.type} (0=Buy, 1=Sell) | Volume: {d.volume} | Price: {d.price} | Profit: ${d.profit:+.2f} | Comment: {d.comment}")
        else:
            print("No deals found in history.")
            
        # Get open positions
        positions = mt5.positions_get()
        if positions:
            print(f"\nOpen positions: {len(positions)}")
            for p in positions:
                print(f"Symbol: {p.symbol} | Type: {p.type} | Volume: {p.volume} | Price: {p.price_open} | Profit: ${p.profit:+.2f}")
        else:
            print("\nNo open positions.")
    else:
        print("Login failed:", mt5.last_error())
    mt5.shutdown()
else:
    print("Initialize failed:", mt5.last_error())
