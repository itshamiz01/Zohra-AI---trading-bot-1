import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for "symbol" or "price" or "get_tick" in scalping_strategy.py
with open("zohra/strategies/scalping_strategy.py", "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f, 1):
        if "symbol" in line.lower() and ("price" in line.lower() or "tick" in line.lower() or "entry" in line.lower()):
            print(f"L{i}: {line.strip()[:180]}")
        elif "eurusd" in line.lower() and ("hardcode" in line.lower() or "=" in line.lower() or "get" in line.lower()):
            print(f"L{i}: {line.strip()[:180]}")
