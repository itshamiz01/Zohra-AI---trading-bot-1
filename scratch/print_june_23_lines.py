import sys

sys.stdout.reconfigure(encoding='utf-8')

def print_june_23_lines(path):
    print(f"\n--- June 23 lines in {path} ---")
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "2026-06-23" in line:
                print(line.strip()[:180])
                count += 1
                if count >= 30:
                    break
    if count == 0:
        print("None found.")

print_june_23_lines("logs/zohra_brain_a.log")
