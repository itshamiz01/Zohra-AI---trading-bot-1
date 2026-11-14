import os
import sys
from datetime import datetime, timedelta
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.config.settings import ACTIVE_ACCOUNT_CONFIGS
import MetaTrader5 as mt5

for acc in ACTIVE_ACCOUNT_CONFIGS:
    init_kwargs = {'path': acc.terminal_path} if acc.terminal_path and os.path.exists(acc.terminal_path) else {}
    if not mt5.initialize(**init_kwargs):
        continue
    if mt5.login(acc.login, password=acc.password, server=acc.server):
        deals = mt5.history_deals_get(datetime.now() - timedelta(days=2), datetime.now()) or []
        print(f"\n=======================================================")
        print(f"=== {acc.name} ({acc.login}) ===")
        print(f"=======================================================")
        
        sym_stats = {}
        for d in deals:
            if d.entry != 1:  # only exit deals
                continue
            s = d.symbol
            if s not in sym_stats:
                sym_stats[s] = {'wins': 0, 'losses': 0, 'pnl': 0.0, 'deals': []}
            sym_stats[s]['pnl'] += d.profit
            if d.profit > 0:
                sym_stats[s]['wins'] += 1
            elif d.profit < 0:
                sym_stats[s]['losses'] += 1
            sym_stats[s]['deals'].append(d)
        
        for s, data in sorted(sym_stats.items(), key=lambda x: x[1]['pnl']):
            total = len(data['deals'])
            wr = (data['wins'] / total * 100) if total > 0 else 0
            print(f"  Symbol {s:<8}: Deals={total:>3}, Wins={data['wins']:>3}, Losses={data['losses']:>3}, WinRate={wr:.1f}%, PnL=${data['pnl']:>7.2f}")
        
        # Show all losing deals
        print("\n  --- Breakdown of Losing Trades ---")
        losing_deals = [d for d in deals if d.entry == 1 and d.profit < 0]
        # Group by comment or reason
        reasons = {}
        for d in losing_deals:
            comm = d.comment if d.comment else "manual/broker"
            reasons[comm] = reasons.get(comm, 0) + 1
        print("  Loss causes:")
        for r, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"    - {r}: {cnt} times")

    mt5.shutdown()
