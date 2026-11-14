import pandas as pd

df = pd.read_csv("logs/mt5_full_deals.csv")
df['time'] = pd.to_datetime(df['time'])
df = df.sort_values(by='time')

# Let's count how many positions are open at any point in time
events = []
for idx, row in df.iterrows():
    if row['entry'] == 'IN':
        events.append((row['time'], 1, row['symbol'], row['type'], row['volume'], row['ticket']))
    elif row['entry'] == 'OUT':
        events.append((row['time'], -1, row['symbol'], row['type'], row['volume'], row['ticket']))

events.sort(key=lambda x: x[0])

active_positions = {}
max_concurrent = 0
concurrent_history = []

for time, event_type, symbol, ptype, vol, ticket in events:
    if event_type == 1:
        active_positions[ticket] = (symbol, ptype, vol)
    else:
        # Find corresponding position to close
        # OUT deal has a different ticket than IN deal in MT5, but order id connects them
        # In our CSV, we don't have order id matching easily unless we match symbol and type (opposite of OUT)
        # Actually, in MT5 history, deals are IN or OUT. Let's just track position counts by matching symbol
        # Let's do a simpler tracking: if IN, increment count for that symbol. If OUT, decrement count for that symbol.
        pass

# Let's check how many positions were opened and closed on July 9
df_july9 = df[df['time'].dt.date == pd.to_datetime('2026-07-09').date()]
print("=== JULY 9 DEALS BY SYMBOL AND COMMENT ===")
print(df_july9.groupby(['symbol', 'comment']).size())

print("\n=== SAMPLE OF PROBE AND SCALE DEALS ON NZDUSD ===")
nzd_deals = df_july9[df_july9['symbol'] == 'NZDUSD'].head(30)
for idx, row in nzd_deals.iterrows():
    print(f"Time: {row['time']} | Ticket: {row['ticket']} | Order: {row['order']} | Type: {row['type']} | Entry: {row['entry']} | Vol: {row['volume']} | Price: {row['price']} | Profit: ${row['profit']} | Comment: {row['comment']}")
