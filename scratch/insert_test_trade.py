import sqlite3

conn = sqlite3.connect('logs/zohra_trades_a.db')
cursor = conn.cursor()

try:
    cursor.execute("""
        INSERT INTO trades (
            trade_id, mt5_ticket, timestamp_open, symbol, direction, 
            entry_price, stop_loss, take_profit, position_size_lots, strategy_used
        ) VALUES (
            'ZHR_TEST_NZDUSD', 57214787536, '2026-06-23T15:00:00', 'NZDUSD', 'SHORT', 
            0.56786, 0.56864, 0.56630, 0.01, 'zohra_v5'
        )
    """)
    conn.commit()
    print("Successfully inserted trade ZHR_TEST_NZDUSD")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
