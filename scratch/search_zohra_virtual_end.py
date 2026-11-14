import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("--- LINES 1850 to 1890 ---")
for j in range(1849, min(len(lines), 1890)):
    print(f"{j+1}: {lines[j].rstrip()}")
print("-------------------------")
