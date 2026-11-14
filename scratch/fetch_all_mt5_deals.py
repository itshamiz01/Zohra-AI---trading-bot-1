import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
import MetaTrader5 as mt5
from zohra.config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TERMINAL_PATH
import datetime as dt
import pandas as pd

init_ok = mt5.initialize(path=MT5_TERMINAL_PATH) if MT5_TERMINAL_PATH else mt5.initialize()
if not init_ok:
    print(f"Failed to initialize MT5: {mt5.last_error()}")
    sys.exit(1)
mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)

# Fetch all history from 2025-01-01 to now
from_dt = dt.datetime(2025, 1, 1)
to_dt = dt.datetime.utcnow() + dt.timedelta(days=1)

deals = mt5.history_deals_get(from_dt, to_dt)
if deals is None:
    print("Failed to get deals history:", mt5.last_error())
else:
    print(f"Total deals found: {len(deals)}")
    
    # Let's convert to a pandas DataFrame and analyze
    records = []
    for d in deals:
        records.append({
            "ticket": d.ticket,
            "order": d.order,
            "time": dt.datetime.fromtimestamp(d.time, dt.timezone.utc).isoformat(),
            "type": "BUY" if d.type == 0 else "SELL" if d.type == 1 else f"OTHER({d.type})",
            "entry": "IN" if d.entry == 0 else "OUT" if d.entry == 1 else "IN/OUT" if d.entry == 2 else f"OTHER({d.entry})",
            "symbol": d.symbol,
            "volume": d.volume,
            "price": d.price,
            "profit": d.profit,
            "commission": d.commission,
            "swap": d.swap,
            "comment": d.comment,
            "magic": d.magic,
            "external_id": d.external_id
        })
        
    df = pd.DataFrame(records)
    print(df.head())
    
    # Calculate some statistics
    df_trades = df[(df['profit'] != 0.0) | (df['commission'] != 0.0) | (df['swap'] != 0.0)]
    print(f"Deals with PnL/Cost: {len(df_trades)}")
    
    total_profit = df_trades['profit'].sum()
    total_commission = df_trades['commission'].sum()
    total_swap = df_trades['swap'].sum()
    net_pnl = total_profit + total_commission + total_swap
    
    print(f"Sum Profit/Loss   : ${total_profit:,.2f}")
    print(f"Sum Commission    : ${total_commission:,.2f}")
    print(f"Sum Swap          : ${total_swap:,.2f}")
    print(f"Net PnL           : ${net_pnl:,.2f}")
    
    # Let's list trades sorted by absolute profit or time
    # Check if there are huge losses
    huge_losses = df_trades[df_trades['profit'] < -500].sort_values(by='profit')
    print(f"\nHUGE LOSSES (>=$500) count: {len(huge_losses)}")
    print(huge_losses.head(20))
    
    # Save to CSV
    df.to_csv("logs/mt5_full_deals.csv", index=False)
    print("Saved MT5 deals to logs/mt5_full_deals.csv")

mt5.shutdown()
