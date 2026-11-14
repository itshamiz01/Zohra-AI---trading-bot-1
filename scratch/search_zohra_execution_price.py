import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("--- LINES 900 to 980 ---")
for j in range(899, 980):
    print(f"{j+1}: {lines[j].rstrip()}")
print("-------------------------")
