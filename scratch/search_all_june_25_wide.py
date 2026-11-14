import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

log_file = 'logs/zohra_engine_a.log'
target_date = "2026-06-25"

print(f"=== ZSC ENTRIES IN {log_file} FOR {target_date} ===")
count = 0
if os.path.exists(log_file):
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if target_date in line and ("filled" in line.lower() or "triggering probe" in line.lower() or "zsc_" in line.lower()):
                print(line.strip())
                count += 1
                if count >= 100:
                    print("... truncated after 100 matches ...")
                    break
else:
    print("Log file does not exist.")
