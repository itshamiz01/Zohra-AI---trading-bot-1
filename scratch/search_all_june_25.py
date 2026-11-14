import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

log_file = 'logs/zohra_engine_a.log'
target_date = "2026-06-25"

print(f"=== ALL USDJPY LOGS IN {log_file} FOR {target_date} ===")
count = 0
if os.path.exists(log_file):
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if target_date in line and "USDJPY" in line and (" 15:" in line or " 16:" in line or " 17:" in line):
                print(line.strip())
                count += 1
                if count >= 200:
                    print("... truncated after 200 matches ...")
                    break
else:
    print("Log file does not exist.")
