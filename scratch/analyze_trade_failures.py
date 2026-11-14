import pandas as pd
import numpy as np

# Load MT5 deals
df = pd.read_csv("logs/mt5_full_deals.csv")

# Sort by time
df = df.sort_values(by='time')

# Filter for trades (deals that have symbol and are entry=OUT or are closed trades)
# In MT5, entry=1 means OUT (closing a position)
# If a deal is entry=OUT, it realizes profit/loss.
df_closed = df[df['entry'] == 'OUT'].copy()

print("=== CLOSED TRADES ANALYSIS (MT5 CURRENT ACCOUNT) ===")
print(f"Total closed trades: {len(df_closed)}")

# Calculate wins/losses
wins = df_closed[df_closed['profit'] > 0]
losses = df_closed[df_closed['profit'] < 0]
breakeven = df_closed[df_closed['profit'] == 0]

print(f"Winning trades: {len(wins)} | Total profit: ${wins['profit'].sum():.2f}")
print(f"Losing trades: {len(losses)} | Total loss: ${losses['profit'].sum():.2f}")
print(f"Breakeven trades: {len(breakeven)}")

win_rate = (len(wins) / len(df_closed)) * 100 if len(df_closed) > 0 else 0
print(f"Win Rate: {win_rate:.2f}%")

print("\n--- LOSSES BY SYMBOL ---")
loss_by_symbol = losses.groupby('symbol')['profit'].agg(['count', 'sum', 'mean']).sort_values(by='sum')
print(loss_by_symbol)

print("\n--- ALL CLOSED TRADES BY SYMBOL ---")
all_by_symbol = df_closed.groupby('symbol')['profit'].agg(['count', 'sum', 'mean'])
print(all_by_symbol)

# Let's inspect comments for losing trades
print("\n--- COMMENTS ON LOSING TRADES ---")
print(losses['comment'].value_counts(dropna=False))

# Let's print details of the largest losing trades
print("\n--- LARGEST LOSING TRADES ---")
largest_losses = losses.sort_values(by='profit').head(15)
for idx, row in largest_losses.iterrows():
    print(f"Time: {row['time']} | Ticket: {row['ticket']} | Symbol: {row['symbol']} | Type: {row['type']} | Vol: {row['volume']} | Price: {row['price']} | Profit: ${row['profit']:.2f} | Comment: {row['comment']}")
