import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/today_logs.txt", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("USDJPY Log Activity starting at 21:00 UTC today:")
found_21 = False
for line in lines:
    if "2026-06-25 21:" in line:
        found_21 = True
    if found_21:
        if "USDJPY" in line or "ZSC_PROBE" in line or "ZSC_SCALE" in line:
            print(line.strip())
