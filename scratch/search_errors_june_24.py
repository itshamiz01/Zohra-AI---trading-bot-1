import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for ERROR or Exception specifically on June 24
def find_errors_june_24(path):
    print(f"\n=== ERRORS ON JUNE 24 IN {path} ===")
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "2026-06-24" in line:
                if "error" in line.lower() or "exception" in line.lower() or "fail" in line.lower():
                    print(line.strip()[:180])
                    count += 1
    if count == 0:
        print("No errors found.")

find_errors_june_24("logs/zohra_brain_a.log")
find_errors_june_24("logs/zohra_engine_a.log")
