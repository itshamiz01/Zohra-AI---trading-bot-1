import sys
sys.stdout.reconfigure(encoding='utf-8')

log_files = ["logs/zohra_engine_a.log", "logs/zohra_brain_a.log"]
for log_file in log_files:
    print(f"=== SEARCHING {log_file} ===")
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if "888568" in line or "20260623_1559" in line or "15:59:28" in line:
                    print(line.strip())
    except Exception as e:
        print(f"Error reading {log_file}: {e}")
