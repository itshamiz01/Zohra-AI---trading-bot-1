import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

log_files = ['logs/zohra_engine_a.log', 'logs/zohra_brain_a.log']
target_date = "2026-06-25"

print(f"=== LOG ENTRIES FOR {target_date} ===")
results = []
for lf in log_files:
    if os.path.exists(lf):
        results.append(f"\nSearching in {lf}:\n")
        with open(lf, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if target_date in line and ("USDJPY" in line or "ZSC_PROBE" in line or "scout" in line.lower() or "guardian" in line.lower()):
                    results.append(line.strip())
    else:
        results.append(f"{lf} does not exist.")

with open("scratch/today_logs.txt", "w", encoding="utf-8") as f:
    for r in results:
        f.write(r + "\n")

print("Logs written to scratch/today_logs.txt. Total matches:", len(results) - len(log_files))
