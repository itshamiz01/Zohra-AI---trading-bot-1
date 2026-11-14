import os
import sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.config.settings import ACTIVE_ACCOUNT_CONFIGS
import MetaTrader5 as mt5

print(f"Found {len(ACTIVE_ACCOUNT_CONFIGS)} active accounts:")
for acc in ACTIVE_ACCOUNT_CONFIGS:
    print(f" - {acc.account_id}: Login={acc.login}, Server={acc.server}, Name={acc.name}, Path={acc.terminal_path}")

for acc in ACTIVE_ACCOUNT_CONFIGS:
    # Initialize with terminal path
    init_kwargs = {}
    if acc.terminal_path and os.path.exists(acc.terminal_path):
        init_kwargs["path"] = acc.terminal_path
    
    if not mt5.initialize(**init_kwargs):
        print(f"MT5 Init failed for {acc.account_id}: {mt5.last_error()}")
        continue
    
    authorized = mt5.login(acc.login, password=acc.password, server=acc.server)
    print(f"\n=======================================================")
    print(f" {acc.name} ({acc.account_id}): Login={acc.login} Server={acc.server} Auth={authorized}")
    print(f"=======================================================")
    if authorized:
        info = mt5.account_info()
        print(f"Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f} | Profit: ${info.profit:.2f} | Margin Free: ${info.margin_free:.2f}")
        
        positions = mt5.positions_get()
        print(f"--- OPEN POSITIONS ({len(positions) if positions else 0}) ---")
        for p in (positions or []):
            side = 'BUY' if p.type == 0 else 'SELL'
            print(f"  [OPEN] Ticket:{p.ticket} {p.symbol} {side} Lots:{p.volume} Open:{p.price_open} Current:{p.price_current} SL:{p.sl} TP:{p.tp} PnL:${p.profit:.2f} Comment:{p.comment}")
        
        from_date = datetime.now() - timedelta(days=5)
        deals = mt5.history_deals_get(from_date, datetime.now())
        print(f"--- CLOSED DEALS (last 5 days, count: {len(deals) if deals else 0}) ---")
        for d in (deals or [])[-25:]:
            side = 'BUY' if d.type == 0 else ('SELL' if d.type == 1 else str(d.type))
            entry = 'IN' if d.entry == 0 else ('OUT' if d.entry == 1 else str(d.entry))
            t_str = datetime.fromtimestamp(d.time).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  [DEAL] {t_str} Ticket:{d.ticket} {d.symbol} {side} {entry} Lots:{d.volume} Price:{d.price} Profit:${d.profit:.2f} Fee:${(d.commission+d.swap):.2f} Comm:{d.comment}")
    
    mt5.shutdown()
