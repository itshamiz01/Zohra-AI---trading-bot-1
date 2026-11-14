import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.brokers.mt5_broker import mt5_broker

if mt5_broker.connect():
    print("✅ Connected to MT5. Closing all positions...")
    closed_count = mt5_broker.close_all_positions(comment="Clean-Start")
    print(f"✅ Successfully closed {closed_count} positions.")
else:
    print("❌ Failed to connect to MetaTrader 5.")
