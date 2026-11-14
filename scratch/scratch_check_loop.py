import MetaTrader5 as mt5
import os
import time
from dotenv import load_dotenv

load_dotenv()

MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print("Failed to initialize MT5")
    exit(1)

print("Running loop for 10 seconds to check stability...")
for i in range(10):
    term = mt5.terminal_info()
    acc = mt5.account_info()
    
    term_conn = term.connected if term is not None else None
    acc_login = acc.login if acc is not None else None
    
    print(f"[{i}] term.connected: {term_conn} | acc.login: {acc_login}")
    time.sleep(1)

mt5.shutdown()
