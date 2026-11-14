import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for "simulated" in zohra.py
with open("zohra.py", "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f, 1):
        if "simulated" in line.lower() or "mode" in line.lower() and ("sim" in line.lower() or "demo" in line.lower()):
            print(f"L{i}: {line.strip()[:180]}")
