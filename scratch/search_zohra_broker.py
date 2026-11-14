import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for "broker" in zohra.py
with open("zohra.py", "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f, 1):
        if "broker" in line.lower() and ("import" in line.lower() or "=" in line.lower()):
            print(f"L{i}: {line.strip()[:180]}")
