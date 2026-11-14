import sqlite3

conn = sqlite3.connect("logs/hie_data.db")
cursor = conn.cursor()
cursor.execute("SELECT symbol, timeframe, COUNT(*) FROM hie_candles GROUP BY symbol, timeframe")
rows = cursor.fetchall()
print("Candle counts per symbol + timeframe:")
for r in rows:
    print(f"  {r[0]} / {r[1]}: {r[2]} candles")
conn.close()
