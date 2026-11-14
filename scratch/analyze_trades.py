import sqlite3
import pandas as pd
import json
import os

dbs = {
    "zohra_trades_a.db": "logs/zohra_trades_a.db",
    "zohra_trades.db": "logs/zohra_trades.db",
    "trades.db": "logs/trades.db"
}

def analyze_db(name, path):
    if not os.path.exists(path):
        return None
    
    conn = sqlite3.connect(path)
    # Get tables
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    
    res = {}
    
    # Analyze trades
    if 'trades' in tables:
        df_trades = pd.read_sql_query("SELECT * FROM trades", conn)
        res['trades'] = df_trades
    else:
        res['trades'] = pd.DataFrame()
        
    # Analyze rejections
    if 'rejected_trades' in tables:
        df_rej = pd.read_sql_query("SELECT * FROM rejected_trades", conn)
        res['rejected_trades'] = df_rej
    else:
        res['rejected_trades'] = pd.DataFrame()
        
    if 'trade_rejections' in tables:
        df_trej = pd.read_sql_query("SELECT * FROM trade_rejections", conn)
        res['trade_rejections'] = df_trej
    else:
        res['trade_rejections'] = pd.DataFrame()
        
    conn.close()
    return res

all_results = {}
for name, path in dbs.items():
    res = analyze_db(name, path)
    if res:
        all_results[name] = res

print("--- SUMMARY OF DATABASES ---")
for name, data in all_results.items():
    print(f"\nDatabase: {name}")
    print(f"  Trades count: {len(data['trades'])}")
    print(f"  Rejected trades count: {len(data['rejected_trades'])}")
    if 'trade_rejections' in data:
        print(f"  Trade rejections count: {len(data['trade_rejections'])}")

# Let's inspect trades from zohra_trades.db (161 rows) and zohra_trades_a.db (10 rows) and trades.db (1 row)
# Let's consolidate all trades
consolidated_trades = []
for db_name, data in all_results.items():
    df = data['trades']
    if len(df) > 0:
        df = df.copy()
        df['source_db'] = db_name
        consolidated_trades.append(df)

if consolidated_trades:
    df_all_trades = pd.concat(consolidated_trades, ignore_index=True)
    # Clean/standardize fields if necessary
    # Let's see some basic info
    print("\n--- CONSOLIDATED TRADES ANALYSIS ---")
    print(f"Total trades: {len(df_all_trades)}")
    
    # Calculate P&L
    # zohra_trades_a.db has pnl_usd, zohra_trades.db has pnl_usd, trades.db has pnl_usd
    # Let's check columns for pnl
    pnl_cols = [c for c in df_all_trades.columns if 'pnl' in c or 'profit' in c]
    print(f"PnL columns found: {pnl_cols}")
    
    # Sum PnL
    df_all_trades['pnl_usd'] = pd.to_numeric(df_all_trades.get('pnl_usd', 0.0)).fillna(0.0)
    total_pnl = df_all_trades['pnl_usd'].sum()
    print(f"Total PnL: ${total_pnl:,.2f}")
    
    winning_trades = df_all_trades[df_all_trades['pnl_usd'] > 0]
    losing_trades = df_all_trades[df_all_trades['pnl_usd'] < 0]
    breakeven_trades = df_all_trades[df_all_trades['pnl_usd'] == 0]
    
    print(f"Wins: {len(winning_trades)}")
    print(f"Losses: {len(losing_trades)}")
    print(f"Breakeven: {len(breakeven_trades)}")
    
    if len(losing_trades) + len(winning_trades) > 0:
        win_rate = len(winning_trades) / (len(winning_trades) + len(losing_trades)) * 100
        print(f"Win Rate (excluding breakeven): {win_rate:.2f}%")
        
    print(f"Total Losses: ${losing_trades['pnl_usd'].sum():,.2f}")
    print(f"Total Wins: ${winning_trades['pnl_usd'].sum():,.2f}")
    
    # Group trades by exit reason
    print("\n--- EXIT REASONS FOR ALL TRADES ---")
    exit_reasons = df_all_trades['reason_for_exit'].value_counts()
    for reason, val in exit_reasons.items():
        print(f"  {reason}: {val}")
        
    # Let's check losing trades exit reasons
    print("\n--- EXIT REASONS FOR LOSING TRADES ---")
    losing_exit_reasons = losing_trades['reason_for_exit'].value_counts()
    for reason, val in losing_exit_reasons.items():
        print(f"  {reason}: {val}")
        
    # Write consolidated trades to CSV
    df_all_trades.to_csv("logs/consolidated_trades.csv", index=False)
    print("\nSaved consolidated trades to logs/consolidated_trades.csv")

# Consolidate all rejections
consolidated_rejections = []
for db_name, data in all_results.items():
    df_rej = data['rejected_trades']
    if len(df_rej) > 0:
        df_rej = df_rej.copy()
        df_rej['source_db'] = db_name
        df_rej['source_table'] = 'rejected_trades'
        # rename columns to match if needed
        consolidated_rejections.append(df_rej)
        
    df_trej = data.get('trade_rejections', pd.DataFrame())
    if len(df_trej) > 0:
        df_trej = df_trej.copy()
        df_trej['source_db'] = db_name
        df_trej['source_table'] = 'trade_rejections'
        consolidated_rejections.append(df_trej)

if consolidated_rejections:
    # Standardize columns for rejections
    # Common columns we want: timestamp, symbol, direction, confidence_score, reason_for_rejection
    standardized = []
    for df in consolidated_rejections:
        std_df = pd.DataFrame()
        std_df['timestamp'] = df.get('timestamp', df.get('created_at', ''))
        std_df['symbol'] = df.get('symbol', '')
        std_df['direction'] = df.get('direction', '')
        std_df['confidence_score'] = df.get('confidence_score', 0)
        # Try both names for rejection reason
        std_df['reason'] = df.get('reason_for_rejection', df.get('rejection_reason', df.get('rejection_category', 'Unknown')))
        std_df['failed_conditions'] = df.get('failed_conditions', '')
        std_df['source_db'] = df['source_db']
        std_df['source_table'] = df['source_table']
        standardized.append(std_df)
        
    df_all_rej = pd.concat(standardized, ignore_index=True)
    print("\n--- CONSOLIDATED REJECTIONS ANALYSIS ---")
    print(f"Total rejections: {len(df_all_rej)}")
    
    # Categorize / summarize rejection reasons
    # Normalize reasons a bit (fill null, strip, limit length)
    df_all_rej['reason'] = df_all_rej['reason'].fillna('Unknown').astype(str).str.strip()
    
    # Group by reason and get counts
    rej_summary = df_all_rej['reason'].value_counts()
    print("\nTop Rejection Reasons:")
    for reason, val in rej_summary.head(15).items():
        print(f"  {reason[:80]}: {val}")
        
    df_all_rej.to_csv("logs/consolidated_rejections.csv", index=False)
    print("\nSaved consolidated rejections to logs/consolidated_rejections.csv")
