import sys
sys.stdout.reconfigure(encoding='utf-8')

log_files = ["logs/zohra_engine_a.log", "logs/zohra_brain_a.log"]
for log_file in log_files:
    print(f"=== SEARCHING {log_file} FOR LOSSES ===")
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if "PnL:" in line or "P&L:" in line or "closed" in line.lower() or "loss" in line.lower():
                    # Print if it has a negative sign or is a close log
                    if any(x in line for x in ["-$", "-0.", "-1.", "-2.", "-3.", "-4.", "-5.", "-6.", "-7.", "-8.", "-9.", "closed", "Loss"]):
                        print(line.strip())
    except Exception as e:
        print(f"Error reading {log_file}: {e}")
