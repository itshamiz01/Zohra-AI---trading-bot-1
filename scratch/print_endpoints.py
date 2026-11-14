with open(r'c:\Users\dell\Desktop\trading_bot\zohra\api\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

def print_lines(start, count):
    for i in range(start - 1, min(start - 1 + count, len(lines))):
        print(f"{i+1}: {lines[i]}")

# Let's search for functions like def search_memories, def get_recent_memories, def analytics_full, def get_trade_replay, etc.
for i, line in enumerate(lines):
    if any(name in line for name in ['def search_memories', 'def get_recent_memories', 'def analytics_full', 'def get_trade_replay', 'route_natural_language_query']):
        print(f"\n--- Found {line.strip()} at line {i+1} ---")
        print_lines(i+1, 20)
