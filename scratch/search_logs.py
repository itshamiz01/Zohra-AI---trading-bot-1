import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def check_log_dates(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    print(f"\n--- LOG FILE: {filepath} ---")
    size_mb = os.path.getsize(filepath) / (1024*1024)
    print(f"Size: {size_mb:.2f} MB")
    
    # Read first 10 lines
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        print("First 10 lines:")
        for _ in range(10):
            line = f.readline()
            if not line:
                break
            print("  ", line.strip())
            
    # Read last 15 lines
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        lines = []
        # Go back line by line
        buffer = ""
        while len(lines) < 20 and pos > 0:
            pos -= 1
            f.seek(pos, os.SEEK_SET)
            char = f.read(1)
            if char == '\n':
                if buffer:
                    lines.append(buffer[::-1])
                    buffer = ""
            else:
                buffer += char
        if buffer:
            lines.append(buffer[::-1])
        print("Last 15 lines:")
        for line in reversed(lines[:15]):
            print("  ", line.strip())

check_log_dates("logs/zohra_engine_a.log")
check_log_dates("logs/zohra_brain_a.log")
