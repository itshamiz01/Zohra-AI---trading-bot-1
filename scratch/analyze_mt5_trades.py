import MetaTrader5 as mt5
from datetime import datetime, timedelta
import sys
import os
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

login = int(os.getenv("MT5_LOGIN"))
password = os.getenv("MT5_PASSWORD")
server = os.getenv("MT5_SERVER")

if not mt5.initialize():
    print("MT5 Init failed")
    sys.exit(1)

if not mt5.login(login, password, server):
    print("MT5 Login failed")
    mt5.shutdown()
    sys.exit(1)

# Query deals for the last 4 days
now = datetime.now()
start_time = now - timedelta(days=4)
deals = mt5.history_deals_get(start_time, now)
mt5.shutdown()

if not deals:
    print("No deals found in the last 4 days.")
    sys.exit(0)

# Convert to DataFrame
records = []
for d in deals:
    if d.symbol == "":
        continue
    records.append({
        "ticket": d.ticket,
        "position_id": d.position_id,
        "time": datetime.fromtimestamp(d.time),
        "symbol": d.symbol,
        "type": d.type, # 0=Buy, 1=Sell
        "entry": d.entry, # 0=In, 1=Out
        "volume": d.volume,
        "price": d.price,
        "profit": d.profit,
        "comment": d.comment
    })

df = pd.DataFrame(records).sort_values("time")

# Reconstruct trades by grouping by position_id
trades = {}
for idx, r in df.iterrows():
    pid = r["position_id"]
    if pid not in trades:
        trades[pid] = {
            "position_id": pid,
            "symbol": r["symbol"],
            "direction": "LONG" if r["type"] == 0 else "SHORT",
            "volume": r["volume"],
            "entry_time": r["time"],
            "entry_price": r["price"],
            "exit_time": None,
            "exit_price": None,
            "profit": 0.0,
            "comment": r["comment"],
            "deals": [r]
        }
    else:
        trades[pid]["deals"].append(r)
        if r["entry"] == 1: # Out
            trades[pid]["exit_time"] = r["time"]
            trades[pid]["exit_price"] = r["price"]
            trades[pid]["profit"] += r["profit"]

# Convert trades to a flat list of closed trades
closed_trades = []
open_trades = []
for pid, t in trades.items():
    # If the last deal was an "Out" deal, we consider it closed
    has_out = any(d["entry"] == 1 for d in t["deals"])
    if has_out:
        # Sum profit of all deals in this position (entry deal has 0 profit, exit deals have the PnL)
        t["profit"] = sum(d["profit"] for d in t["deals"])
        # Find exit time and price from the last deal
        out_deals = [d for d in t["deals"] if d["entry"] == 1]
        if out_deals:
            t["exit_time"] = out_deals[-1]["time"]
            t["exit_price"] = out_deals[-1]["price"]
            t["exit_comment"] = out_deals[-1]["comment"]
        closed_trades.append(t)
    else:
        # It's an open position
        t["profit"] = sum(d["profit"] for d in t["deals"])
        open_trades.append(t)

print(f"Total closed trades found: {len(closed_trades)}")
print(f"Total open trades found: {len(open_trades)}")

# Define the modification cutoff time: June 23, 2026, 22:07 UTC
# In local time (India is UTC+5:30), that is June 24, 2026, 03:37 AM
cutoff = datetime(2026, 6, 24, 3, 37)

print(f"Cutoff Time (Local): {cutoff}")

def calc_stats(trade_list, label):
    print(f"\n==========================================")
    print(f"STATISTICS FOR: {label}")
    print(f"==========================================")
    n_trades = len(trade_list)
    if n_trades == 0:
        print("No trades in this period.")
        return
    
    profits = np.array([t["profit"] for t in trade_list])
    wins = profits[profits > 0]
    losses = profits[profits < 0]
    
    win_rate = (len(wins) / n_trades) * 100 if n_trades > 0 else 0
    total_gain = sum(wins)
    total_loss = abs(sum(losses))
    
    profit_factor = total_gain / total_loss if total_loss > 0 else (float('inf') if total_gain > 0 else 1.0)
    avg_winner = np.mean(wins) if len(wins) > 0 else 0.0
    avg_loser = np.mean(losses) if len(losses) > 0 else 0.0
    
    # Drawdown calculation based on cumulative profit sequence
    cum_profit = np.cumsum(profits)
    peaks = np.maximum.accumulate(cum_profit)
    # If starting balance is 100k
    drawdowns = peaks - cum_profit
    max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
    
    print(f"Number of trades      : {n_trades}")
    print(f"Win Rate              : {win_rate:.2f}%")
    print(f"Profit Factor         : {profit_factor:.2f}")
    print(f"Average Winner        : ${avg_winner:+.2f}")
    print(f"Average Loser         : ${avg_loser:+.2f}")
    print(f"Max Drawdown (PnL Peak to Valley): ${max_drawdown:.2f}")
    
    # Long vs Short
    longs = [t for t in trade_list if t["direction"] == "LONG"]
    shorts = [t for t in trade_list if t["direction"] == "SHORT"]
    
    print(f"\nLong Trades Performance:")
    print(f"  Count: {len(longs)}")
    if longs:
        l_profits = [t["profit"] for t in longs]
        l_wr = (sum(1 for p in l_profits if p > 0) / len(longs)) * 100
        print(f"  Win Rate: {l_wr:.2f}% | PnL: ${sum(l_profits):+.2f}")
        
    print(f"Short Trades Performance:")
    print(f"  Count: {len(shorts)}")
    if shorts:
        s_profits = [t["profit"] for t in shorts]
        s_wr = (sum(1 for p in s_profits if p > 0) / len(shorts)) * 100
        print(f"  Win Rate: {s_wr:.2f}% | PnL: ${sum(s_profits):+.2f}")
        
    # Symbol-wise performance
    print(f"\nSymbol-wise Performance:")
    syms = {}
    for t in trade_list:
        sym = t["symbol"]
        if sym not in syms:
            syms[sym] = []
        syms[sym].append(t)
    for sym, stlist in sorted(syms.items()):
        sprofits = [t["profit"] for t in stlist]
        swins = sum(1 for p in sprofits if p > 0)
        swr = (swins / len(stlist)) * 100
        print(f"  {sym:<10}: Count={len(stlist):<3} | Win Rate={swr:.1f}% | Net PnL=${sum(sprofits):+.2f}")
        
    # Hour-wise performance (using entry time hour)
    print(f"\nHour-wise Performance (Local Time Hour):")
    hours = {}
    for t in trade_list:
        hr = t["entry_time"].hour
        if hr not in hours:
            hours[hr] = []
        hours[hr].append(t)
    for hr, htlist in sorted(hours.items()):
        hprofits = [t["profit"] for t in htlist]
        hwins = sum(1 for p in hprofits if p > 0)
        hwr = (hwins / len(htlist)) * 100
        print(f"  Hour {hr:02d}: Count={len(htlist):<3} | Win Rate={hwr:.1f}% | Net PnL=${sum(hprofits):+.2f}")

# Filter closed trades
before_trades = [t for t in closed_trades if t["entry_time"] < cutoff]
after_trades = [t for t in closed_trades if t["entry_time"] >= cutoff]

calc_stats(before_trades, "BEFORE MODIFICATIONS")
calc_stats(after_trades, "AFTER MODIFICATIONS")
