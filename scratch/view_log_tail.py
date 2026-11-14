import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

log_file = 'logs/zohra_engine_a.log'
if os.path.exists(log_file):
    print(f"=== LAST 50 LINES OF {log_file} ===")
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    for l in lines[-50:]:
        print(l.strip())
else:
    print(f"{log_file} does not exist.")
