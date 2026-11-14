import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_files = ["logs/zohra_engine_a.log", "logs/zohra_brain_a.log"]
keywords = ["error", "exception", "fail", "db", "sqlite", "trades", "lock", "write"]

for filepath in log_files:
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        continue
    
    print(f"\n========================================\nSEARCHING LOGS: {filepath}\n========================================")
    
    count = 0
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f, 1):
            line_lower = line.lower()
            # If line has traceback or database errors
            if any(k in line_lower for k in ["sqlite", "database", "log_equity", "log_trade", "locked", "readonly"]):
                print(f"Line {line_num}: {line.strip()}")
                count += 1
                if count > 50:
                    print("... Truncated after 50 matches ...")
                    break
    print(f"Total database-related messages in {filepath}: {count}")
