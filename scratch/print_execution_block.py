import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("=== Zohra.py Decision Block (Lines 450-640) ===")
start = 450
end = 640
for i in range(start-1, min(end, len(lines))):
    print(f"{i+1}: {lines[i].rstrip()}")
