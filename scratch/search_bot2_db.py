import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("trading_bot2/database.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "sqlite" in line or "db" in line or "connect" in line:
            print(f"Line {i+1}: {line.strip()}")
