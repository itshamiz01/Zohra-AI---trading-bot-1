import sqlite3
import os

db_path = "logs/zohra_trades.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n--- ALL RECENT TRADES ---")
    rows = cursor.execute("SELECT id, trade_id, symbol, direction, entry_price, exit_price, pnl_usd, strategy_used, timestamp_open, timestamp_close, reason_for_exit FROM trades ORDER BY id DESC LIMIT 30").fetchall()
    for r in rows:
        print(f"ID: {r['id']} | Date: {r['timestamp_open'][:10]} | Symbol: {r['symbol']} | Dir: {r['direction']} | PnL: ${r['pnl_usd']} | Strategy: {r['strategy_used']} | ExitReason: {r['reason_for_exit']}")
        
    print("\n--- PNL SUMMARY BY DATE ---")
    pnl_by_date = cursor.execute("""
        SELECT date(timestamp_open) as trade_date, 
               COUNT(*) as total_trades,
               SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl_usd < 0 THEN 1 ELSE 0 END) as losses,
               SUM(pnl_usd) as net_pnl
        FROM trades 
        GROUP BY trade_date 
        ORDER BY trade_date DESC
    """).fetchall()
    for r in pnl_by_date:
        print(f"Date: {r['trade_date']} | Total: {r['total_trades']} | Wins: {r['wins']} | Losses: {r['losses']} | Net PnL: ${r['net_pnl']:.2f}")
        
    conn.close()
else:
    print("Database not found.")
