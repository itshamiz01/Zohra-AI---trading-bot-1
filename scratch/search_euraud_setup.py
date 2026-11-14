import sys
sys.stdout.reconfigure(encoding='utf-8')

log_files = ["logs/zohra_engine_a.log", "logs/zohra_brain_a.log"]
for log_file in log_files:
    print(f"=== SEARCHING {log_file} ===")
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if "21:29" in line or "21:28" in line:
                    if any(x in line for x in ["EURAUD", "888568", "ruling", "ruling:", "MomentumScalp"]):
                        print(line.strip())
    except Exception as e:
        print(f"Error reading {log_file}: {e}")
