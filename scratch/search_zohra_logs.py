import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

# Let's search zohra/logs/zohra_brain.log for logs on June 23 around 15:50 to 16:15 UTC
log_file = "zohra/logs/zohra_brain.log"
print(f"Searching: {log_file}")

with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "2026-06-23" in line:
            # check if hour is 15:5 or 15:4 or 16:0 or 16:1
            if any(x in line for x in [" 15:5", " 15:4", " 16:0", " 16:1", " 15:00"]):
                print(line.strip())
