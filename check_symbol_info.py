import MetaTrader5 as mt5
import sys
import os
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

init_ok = mt5.initialize(path=MT5_TERMINAL_PATH) if MT5_TERMINAL_PATH else mt5.initialize()
if not init_ok:
    print("Failed to initialize MT5:", mt5.last_error())
    sys.exit(1)

for symbol in ["XAGUSD", "XAUUSD", "EURAUD", "NZDJPY"]:
    info = mt5.symbol_info(symbol)
    if info:
        print(f"SYMBOL: {symbol}")
        print(f"  trade_tick_value: {info.trade_tick_value}")
        print(f"  trade_tick_size: {info.trade_tick_size}")
        print(f"  volume_step: {info.volume_step}")
        print(f"  volume_min: {info.volume_min}")
        print(f"  volume_max: {info.volume_max}")
        print(f"  point: {info.point}")
        print(f"  trade_contract_size: {info.trade_contract_size}")
    else:
        print(f"SYMBOL {symbol} NOT FOUND")

mt5.shutdown()
