import sys

sys.stdout.reconfigure(encoding='utf-8')

def find_any_dates(path):
    print(f"\n--- Analyzing dates in {path} ---")
    dates = set()
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            # Look for [YYYY-MM-DD
            if line.startswith("["):
                parts = line.split(" ")
                if len(parts) > 0:
                    date_str = parts[0][1:]
                    dates.add(date_str)
    print("Dates found in log:")
    for d in sorted(list(dates)):
        print(f"  {d}")

find_any_dates("logs/zohra_brain_a.log")
find_any_dates("logs/zohra_engine_a.log")
