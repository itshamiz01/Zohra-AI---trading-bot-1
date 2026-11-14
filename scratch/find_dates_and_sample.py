import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

def find_dates_and_sample(filepath):
    print(f"\n--- Analyzing dates in {filepath} ---")
    dates = set()
    sample_lines = []
    
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("["):
                parts = line.split(" ")
                if len(parts) > 0:
                    date_str = parts[0][1:]
                    dates.add(date_str)
            if "2026-06-23" in line and len(sample_lines) < 20:
                sample_lines.append(line.strip())
                
    print("Dates found in log:")
    for d in sorted(list(dates)):
        print(f"  {d}")
        
    print("\nSample lines containing '2026-06-23':")
    for l in sample_lines:
        print(f"  {l[:180]}")

find_dates_and_sample("zohra/logs/zohra_brain.log")
