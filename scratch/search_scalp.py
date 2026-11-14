import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("zohra/strategies/scalping_strategy.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("Functions in scalping_strategy.py:")
for i, line in enumerate(lines):
    if line.strip().startswith("def "):
        print(f"L{i+1}: {line.strip()}")
