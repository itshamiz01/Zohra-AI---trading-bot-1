import os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
import MetaTrader5 as mt5
from zohra.config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_TERMINAL_PATH
import datetime as dt

init_ok = mt5.initialize(path=MT5_TERMINAL_PATH) if MT5_TERMINAL_PATH else mt5.initialize()
if not init_ok:
    print(f"Failed to initialize MT5: {mt5.last_error()}")
    sys.exit(1)
mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)

acc = mt5.account_info()
print(f"Balance  : ${acc.balance:,.2f}")
print(f"Equity   : ${acc.equity:,.2f}")
pnl = acc.equity - acc.balance
print(f"Float P&L: ${pnl:+,.2f}")
print()

# Open positions
pos = mt5.positions_get()
if pos:
    print(f"=== OPEN POSITIONS ({len(pos)}) ===")
    for p in pos:
        direction = "LONG" if p.type == 0 else "SHORT"
        print(f"  {p.symbol} {direction} | Lots={p.volume} | Entry={p.price_open:.5f} | Current={p.price_current:.5f} | PnL=${p.profit:+.2f} | SL={p.sl:.5f} | TP={p.tp:.5f}")
else:
    print("No open positions.")

print()

# Closed trades last 48h
now  = dt.datetime.utcnow()
from_dt = now - dt.timedelta(hours=48)
deals = mt5.history_deals_get(from_dt, now)
if deals:
    closed = [d for d in deals if d.profit != 0 and d.symbol != ""]
    print(f"=== CLOSED TRADES (last 48h) — {len(closed)} trades ===")
    total = 0.0
    wins = 0
    losses = 0
    for d in closed:
        total += d.profit
        if d.profit > 0:
            wins += 1
        else:
            losses += 1
        side = "BUY" if d.type == 0 else "SELL"
        print(f"  {d.symbol:<10} {side:<5} | P&L=${d.profit:+.2f:>8} | Entry={d.price:.5f} | {d.comment}")
    print()
    print(f"  Total P&L  : ${total:+.2f}")
    print(f"  Wins       : {wins}")
    print(f"  Losses     : {losses}")
    wr = (wins/(wins+losses)*100) if (wins+losses) > 0 else 0
    print(f"  Win Rate   : {wr:.1f}%")
else:
    print("No closed trades in last 48h.")

mt5.shutdown()
