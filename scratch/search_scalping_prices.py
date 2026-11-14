import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for tick, mt5_broker, ask, bid, price in scalping_strategy.py
terms = ["tick", "mt5_broker", "ask", "bid", "price", "get_ohlcv"]
with open("zohra/strategies/scalping_strategy.py", "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f, 1):
        if any(t in line.lower() for t in terms) and ("=" in line.lower() or "call" in line.lower() or "get" in line.lower() or "return" in line.lower()):
            print(f"L{i}: {line.strip()[:180]}")
