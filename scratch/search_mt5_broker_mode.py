import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for "simulated" in zohra/brokers/mt5_broker.py
with open("zohra/brokers/mt5_broker.py", "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f, 1):
        if "simulated" in line.lower() or "mode" in line.lower() or "simbroker" in line.lower():
            print(f"L{i}: {line.strip()[:180]}")
