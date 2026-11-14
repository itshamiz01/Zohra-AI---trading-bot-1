import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.brokers.mt5_broker import mt5_broker

if mt5_broker.connect():
    print("✅ MT5 Connected successfully.")
    positions = mt5_broker.get_open_positions()
    print(f"Total open positions on MT5 account: {len(positions)}")
    for pos in positions:
        print(f"Ticket: {pos.get('ticket')} | Symbol: {pos.get('symbol')} | Direction: {pos.get('direction')} | Lots: {pos.get('lots')} | Entry: {pos.get('entry_price')} | Profit: ${pos.get('profit')}")
    account = mt5_broker.get_account_info()
    if account:
        print(f"Account Balance: ${account.get('balance')} | Equity: ${account.get('equity')} | Free Margin: ${account.get('free_margin')}")
else:
    print("❌ Failed to connect to MetaTrader 5.")
