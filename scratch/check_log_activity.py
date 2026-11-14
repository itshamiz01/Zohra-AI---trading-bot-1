import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

def check_log_dates(filepath):
    print(f"\n--- Log: {filepath} ---")
    if not os.path.exists(filepath):
        print("Does not exist.")
        return
    
    size = os.path.getsize(filepath)
    print(f"Size: {size} bytes")
    
    # Read first 10 lines
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        print("First 10 lines:")
        for _ in range(10):
            line = f.readline()
            if not line:
                break
            print(f"  {line.strip()}")
            
    # Read last 20 lines
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        f.seek(max(0, size - 4000))
        lines = f.readlines()
        print(f"Last 15 lines of {filepath}:")
        for line in lines[-15:]:
            print(f"  {line.strip()}")

check_log_dates("logs/zohra_brain_a.log")
check_log_dates("logs/zohra_engine_a.log")
check_log_dates("logs/zohra_engine.log")
