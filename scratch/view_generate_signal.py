import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for def generate_signal in scalping_strategy.py and print the first 60 lines of the function
with open("zohra/strategies/scalping_strategy.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

found = -1
for i, line in enumerate(lines):
    if "def generate_signal" in line:
        found = i
        break

if found != -1:
    print(f"Found def generate_signal at line {found+1}:")
    for j in range(found, min(len(lines), found + 80)):
        print(f"L{j+1}: {lines[j].strip()}")
else:
    print("def generate_signal not found.")
