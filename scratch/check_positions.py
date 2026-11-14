import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.config.settings import ACTIVE_ACCOUNT_CONFIGS
import MetaTrader5 as mt5

for acc in ACTIVE_ACCOUNT_CONFIGS:
    if mt5.initialize(login=acc.login, server=acc.server, password=acc.password):
        info = mt5.account_info()
        positions = mt5.positions_get() or []
        print(f"\n==========================================")
        print(f"{acc.name} (Login: {acc.login})")
        print(f"Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f} | Free Margin: ${info.margin_free:.2f}")
        print(f"Active Positions: {len(positions)}")
        for p in positions:
            side = 'BUY' if p.type == 0 else 'SELL'
            print(f"  * {p.symbol} {side} | Vol: {p.volume} | Open: {p.price_open} | Cur: {p.price_current} | SL: {p.sl} | TP: {p.tp} | Profit: ${p.profit:.2f}")
        mt5.shutdown()
