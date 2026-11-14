import MetaTrader5 as mt5
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
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

# Get open positions
positions = mt5.positions_get()
print(f"=== CURRENT OPEN POSITIONS: {len(positions) if positions else 0} ===")

if positions:
    import pandas as pd
    records = []
    for p in positions:
        records.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == 0 else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "price_current": p.price_current,
            "profit": p.profit,
            "comment": p.comment
        })
    df = pd.DataFrame(records)
    print(df.to_string())
else:
    print("No open positions found.")

# Account balance and equity
acc = mt5.account_info()
if acc:
    print(f"\nAccount Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Floating PnL: ${acc.profit:+.2f}")

mt5.shutdown()
