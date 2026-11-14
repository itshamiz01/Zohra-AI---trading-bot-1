import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/today_logs.txt", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("Risk check logs for USDJPY between 15:00 and 17:30 UTC today:")
count = 0
for line in lines:
    if "USDJPY" in line and ("2026-06-25 15:" in line or "2026-06-25 16:" in line or "2026-06-25 17:" in line):
        if "scout" in line.lower() or "guardian" in line.lower() or "probe" in line.lower() or "scale" in line.lower() or "veto" in line.lower() or "filled" in line.lower():
            print(line.strip())
            count += 1
            if count >= 100:
                print("... truncated after 100 matches ...")
                break
