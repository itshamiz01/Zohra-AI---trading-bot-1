import MetaTrader5 as mt5
import os
from dotenv import load_dotenv

load_dotenv()

MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print("Failed to initialize MT5")
    exit(1)

term = mt5.terminal_info()
print("Terminal info:")
if term is not None:
    print(f"  connected: {term.connected}")
    print(f"  dlls_allowed: {term.dlls_allowed}")
    print(f"  trade_allowed (Algo Trading button status): {term.trade_allowed}")
    print(f"  tradeapi_disabled: {term.tradeapi_disabled}")
    print(f"  name: {term.name}")
else:
    print("term is None")

acc = mt5.account_info()
print("Account info:")
if acc is not None:
    print(f"  login: {acc.login}")
    print(f"  server: {acc.server}")
    print(f"  trade_allowed (Account level permission): {acc.trade_allowed}")
    print(f"  trade_expert (EA trading permission): {acc.trade_expert}")
    print(f"  equity: {acc.equity}")
    print(f"  balance: {acc.balance}")
else:
    print("acc is None")

mt5.shutdown()
