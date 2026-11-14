import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("=== Searching for trade entry or scoring in zohra.py ===")
for idx, line in enumerate(lines):
    if any(k in line for k in ["scorer.calculate_score", "open_position", "execute_trade", "open_trade", "open_market"]):
        print(f"Line {idx+1}: {line.strip()}")
