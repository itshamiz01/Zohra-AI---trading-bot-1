import pandas as pd

df = pd.read_csv("logs/mt5_full_deals.csv")
df['time'] = pd.to_datetime(df['time'])
df['date'] = df['time'].dt.date

print("=== DEALS COUNT BY DATE ===")
print(df.groupby('date').size())

print("\n=== CLOSED TRADES COUNT BY DATE ===")
df_closed = df[df['entry'] == 'OUT'].copy()
df_closed['date'] = df_closed['time'].dt.date
print(df_closed.groupby('date').size())

print("\n=== PNL BY DATE ===")
print(df_closed.groupby('date')['profit'].sum())
