import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("--- LINES 900 to 1100 ---")
for j in range(899, min(len(lines), 1100)):
    print(f"{j+1}: {lines[j].rstrip()}")
print("-------------------------")
