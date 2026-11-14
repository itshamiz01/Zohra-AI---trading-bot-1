import pandas as pd
import json

df = pd.read_csv("logs/mt5_full_deals.csv")

print("--- ALL UNIQUE SYMBOLS ---")
print(df['symbol'].unique())

print("\n--- DEALS WITHOUT SYMBOL (DEPOSITS/WITHDRAWALS/ETC) ---")
no_symbol = df[df['symbol'].isna() | (df['symbol'] == '')]
print(no_symbol)

print("\n--- TYPES OF DEALS ---")
print(df['type'].value_counts())

print("\n--- ENTRY TYPE OF DEALS ---")
print(df['entry'].value_counts())

print("\n--- TOTAL PNL AND MAGIC NUMBERS ---")
print(df.groupby('magic')['profit'].sum())

# Let's find out how the balance went to $164.71
# If the initial deposit was $100,000, let's check if there was a balance reset or deposit of $100k
# Check all rows where magic == 0 or profit is large
large_deals = df[df['profit'].abs() > 100].sort_values(by='profit')
print("\n--- LARGE DEALS (>=$100 in magnitude) ---")
print(large_deals)

# Let's trace the balance over time
df_sorted = df.sort_values(by='time')
balance = 0.0
records = []
for index, row in df_sorted.iterrows():
    profit = row['profit'] if not pd.isna(row['profit']) else 0.0
    commission = row['commission'] if not pd.isna(row['commission']) else 0.0
    swap = row['swap'] if not pd.isna(row['swap']) else 0.0
    change = profit + commission + swap
    balance += change
    records.append({
        "time": row['time'],
        "symbol": row['symbol'],
        "type": row['type'],
        "entry": row['entry'],
        "volume": row['volume'],
        "price": row['price'],
        "profit": row['profit'],
        "balance": balance,
        "comment": row['comment']
    })

df_balance = pd.DataFrame(records)
df_balance.to_csv("logs/balance_history.csv", index=False)
print("\nSaved balance history to logs/balance_history.csv")
print("Ending balance trace:", balance)
print("First 10 records of balance history:")
print(df_balance.head(10))
print("Last 10 records of balance history:")
print(df_balance.tail(10))
