import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = "logs/zohra_engine_a.log"
target_date = "2026-07-09"

if os.path.exists(log_path):
    print(f"=== ENGINE LOGS FOR {target_date} (FIRST 100 LINES) ===")
    count = 0
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if target_date in line:
                print(line.strip())
                count += 1
                if count >= 100:
                    break
    print(f"Printed {count} lines.")
    
    print(f"\n=== ENGINE LOGS FOR {target_date} (LAST 100 LINES) ===")
    lines_today = []
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if target_date in line:
                lines_today.append(line.strip())
    for line in lines_today[-100:]:
        print(line)
    print(f"Total lines for today: {len(lines_today)}")
else:
    print(f"Log not found: {log_path}")
