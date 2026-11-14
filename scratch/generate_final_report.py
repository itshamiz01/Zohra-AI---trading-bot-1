import sqlite3
import pandas as pd
import json
import os

# 1. MT5 Live Account Analysis (since June 30, 2026)
df_mt5 = pd.read_csv("logs/mt5_full_deals.csv")
df_mt5['time'] = pd.to_datetime(df_mt5['time'])
df_mt5_closed = df_mt5[df_mt5['entry'] == 'OUT'].copy()

mt5_total = len(df_mt5_closed)
mt5_wins = len(df_mt5_closed[df_mt5_closed['profit'] > 0])
mt5_losses = len(df_mt5_closed[df_mt5_closed['profit'] < 0])
mt5_profit = df_mt5_closed[df_mt5_closed['profit'] > 0]['profit'].sum()
mt5_loss = df_mt5_closed[df_mt5_closed['profit'] < 0]['profit'].sum()
mt5_net = mt5_profit + mt5_loss
mt5_win_rate = (mt5_wins / mt5_total * 100) if mt5_total > 0 else 0

# 2. Database historical analysis (combining all local DB records)
db_trades = []
for db_name in ["logs/zohra_trades_a.db", "logs/zohra_trades.db"]:
    if os.path.exists(db_name):
        conn = sqlite3.connect(db_name)
        try:
            df = pd.read_sql_query("SELECT id, timestamp_open, symbol, direction, entry_price, exit_price, pnl_usd, reason_for_exit FROM trades", conn)
            df['db_source'] = db_name
            db_trades.append(df)
        except Exception as e:
            print(f"Error reading trades from {db_name}: {e}")
        conn.close()

if db_trades:
    df_db_trades = pd.concat(db_trades, ignore_index=True)
    db_total = len(df_db_trades)
    db_wins = len(df_db_trades[df_db_trades['pnl_usd'] > 0])
    db_losses = len(df_db_trades[df_db_trades['pnl_usd'] < 0])
    db_breakeven = len(df_db_trades[df_db_trades['pnl_usd'] == 0])
    db_profit = df_db_trades[df_db_trades['pnl_usd'] > 0]['pnl_usd'].sum()
    db_loss = df_db_trades[df_db_trades['pnl_usd'] < 0]['pnl_usd'].sum()
    db_net = db_profit + db_loss
else:
    db_total = db_wins = db_losses = db_breakeven = db_profit = db_loss = db_net = 0

# 3. Rejections Analysis
db_rejections = []
for db_name in ["logs/zohra_trades_a.db", "logs/zohra_trades.db"]:
    if os.path.exists(db_name):
        conn = sqlite3.connect(db_name)
        # Check rejected_trades table
        try:
            df = pd.read_sql_query("SELECT timestamp, symbol, reason_for_rejection FROM rejected_trades", conn)
            df['db_source'] = db_name
            df.rename(columns={'reason_for_rejection': 'reason'}, inplace=True)
            db_rejections.append(df)
        except Exception:
            pass
        # Check trade_rejections table
        try:
            df = pd.read_sql_query("SELECT timestamp, symbol, rejection_reason FROM trade_rejections", conn)
            df['db_source'] = db_name
            df.rename(columns={'rejection_reason': 'reason'}, inplace=True)
            db_rejections.append(df)
        except Exception:
            pass
        conn.close()

if db_rejections:
    df_rej = pd.concat(db_rejections, ignore_index=True)
    df_rej['reason'] = df_rej['reason'].fillna('').astype(str).str.strip()
    # Filter empty reasons (some records have blank reason)
    df_rej_clean = df_rej[df_rej['reason'] != '']
    rej_total = len(df_rej_clean)
    rej_top = df_rej_clean['reason'].value_counts().head(10)
else:
    rej_total = 0
    rej_top = pd.Series()

print("====================================================")
print("FINAL REPORT DATA SUMMARY")
print("====================================================")
print(f"LIVE MT5 ACCOUNT STATS (Since June 30, 2026):")
print(f"  Initial Deposit       : $200.00 (on June 30, 2026)")
print(f"  Current Balance       : $164.71")
print(f"  Actual Net Loss       : ${abs(mt5_net):.2f} (drawn down by 17.65%)")
print(f"  Total Trades Taken    : {mt5_total}")
print(f"  Winning Trades        : {mt5_wins} (Profit: ${mt5_profit:.2f})")
print(f"  Losing Trades         : {mt5_losses} (Loss: ${mt5_loss:.2f})")
print(f"  Win Rate              : {mt5_win_rate:.2f}%")
print()
print(f"DATABASE RECORDED STATS (Day One to Today - Includes Demo/Simulated):")
print(f"  Total Database Trades : {db_total}")
print(f"  Database Wins         : {db_wins} (${db_profit:.2f})")
print(f"  Database Losses       : {db_losses} (${db_loss:.2f})")
print(f"  Database Breakeven    : {db_breakeven}")
print(f"  Database Net PnL      : ${db_net:+.2f}")
print()
print(f"REJECTIONS SUMMARY (Day One to Today):")
print(f"  Total Trades Rejected : {rej_total}")
print(f"  Top Rejection Reasons:")
for reason, count in rej_top.items():
    print(f"    - {reason}: {count} times")
print("====================================================")

# Save summary text to a file so it can be viewed if needed
with open("logs/trading_summary_report.txt", "w", encoding='utf-8') as f:
    f.write("=== ZOHRA TRADING BOT PERFORMANCE & AUDIT REPORT ===\n\n")
    f.write("1. LIVE ACCOUNT PERFORMANCE (MT5 Login #10011542635)\n")
    f.write(f"   - Initial Capital   : $200.00 (Deposited 2026-06-30)\n")
    f.write(f"   - Current Balance   : $164.71\n")
    f.write(f"   - Realized Net PnL  : ${mt5_net:.2f}\n")
    f.write(f"   - Total Trades      : {mt5_total}\n")
    f.write(f"   - Wins / Losses     : {mt5_wins} Wins / {mt5_losses} Losses\n")
    f.write(f"   - Win Rate          : {mt5_win_rate:.2f}%\n\n")
    f.write("2. REJECTIONS SUMMARY\n")
    f.write(f"   - Total Rejections  : {rej_total}\n")
    f.write("   - Primary Veto Reasons:\n")
    for reason, count in rej_top.items():
        f.write(f"     * {reason}: {count} times\n")
