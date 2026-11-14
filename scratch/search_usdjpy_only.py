import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

log_files = ['logs/zohra_engine_a.log', 'logs/zohra_brain_a.log']
target_date = "2026-06-25"

for log_file in log_files:
    print(f"\n=== USDJPY SCOUT TRADING IN {log_file} FOR {target_date} ===")
    count = 0
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if target_date in line and "USDJPY" in line and (" 15:" in line or " 16:" in line or " 17:" in line):
                    if "triggering probe" in line.lower() or "filled" in line.lower():
                        print(line.strip())
                        count += 1
                        if count >= 100:
                            print("... truncated after 100 matches ...")
                            break
    else:
        print("Log file does not exist.")
