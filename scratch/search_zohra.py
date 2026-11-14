import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("zohra/core/symbol_worker.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("--- LINES 101 to 177 ---")
for j in range(100, min(len(lines), 177)):
    print(f"{j+1}: {lines[j].rstrip()}")
print("-------------------------")
