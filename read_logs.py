import sqlite3
import sys

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('logs/trades.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print('=== SYSTEM LOGS (last 40) ===')
cur.execute('SELECT timestamp, level, message FROM system_logs ORDER BY id DESC LIMIT 40')
rows = cur.fetchall()
for r in reversed(rows):
    msg = r["message"].encode('ascii', errors='replace').decode('ascii')
    print(f'[{r["timestamp"]}] [{r["level"]}] {msg}')

print()
print('=== OPEN TRADES ===')
cur.execute("SELECT * FROM trades WHERE timestamp_close IS NULL")
trades = cur.fetchall()
if trades:
    for t in trades:
        print(dict(t))
else:
    print('No open trades yet')

print()
print('=== SIGNALS DETECTED ===')
cur.execute('SELECT * FROM signals ORDER BY id DESC LIMIT 10')
sigs = cur.fetchall()
if sigs:
    for s in sigs:
        print(dict(s))
else:
    print('No signals yet')

print()
print('=== EQUITY LOG (last 5) ===')
cur.execute('SELECT * FROM equity_curve ORDER BY id DESC LIMIT 5')
eq = cur.fetchall()
if eq:
    for e in eq:
        print(dict(e))
else:
    print('No equity records yet')

conn.close()
