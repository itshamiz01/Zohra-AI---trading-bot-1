import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("trading_bot2/config.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        print(f"Line {i+1}: {line.rstrip()}")
