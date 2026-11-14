import os
import sys
import MetaTrader5 as mt5

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.config.settings import ACTIVE_ACCOUNT_CONFIGS

print(f"Loaded {len(ACTIVE_ACCOUNT_CONFIGS)} active accounts.")

total_open = 0

for acc in ACTIVE_ACCOUNT_CONFIGS:
    print(f"\n--- Checking {acc.account_id} ({acc.name}) | Login: {acc.login} ---")
    mt5.shutdown()
    init_res = mt5.initialize(
        path=acc.terminal_path,
        login=acc.login,
        password=acc.password,
        server=acc.server,
    )
    if not init_res:
        # try path only
        init_res = mt5.initialize(path=acc.terminal_path)
    
    if not init_res:
        print(f"❌ Failed to initialize MT5 for {acc.account_id}: {mt5.last_error()}")
        continue
    
    info = mt5.account_info()
    if not info:
        print(f"❌ Cannot retrieve account info: {mt5.last_error()}")
        continue
    
    print(f"✅ Connected to Login: {info.login}, Server: {info.server}, Equity: {info.equity}")
    positions = mt5.positions_get()
    if positions is None:
        print(f"Positions query returned None: {mt5.last_error()}")
    elif len(positions) == 0:
        print("No open positions.")
    else:
        print(f"Found {len(positions)} open position(s):")
        for p in positions:
            total_open += 1
            ptype = "BUY" if p.type == 0 else "SELL"
            print(f"  Ticket: {p.ticket} | {p.symbol} {ptype} {p.volume} lots | Open: {p.price_open} | Profit: ${p.profit:.2f}")

mt5.shutdown()
print(f"\nTotal open positions across all accounts: {total_open}")
