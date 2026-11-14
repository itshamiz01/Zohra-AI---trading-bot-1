import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for the symbols specifically on June 23
def search_june_23_symbols(path):
    print(f"\n==========================================")
    print(f"File: {path} (June 23 entries)")
    print(f"==========================================")
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "2026-06-23" in line and any(sym in line for sym in ["EURAUD", "EURCAD", "GBPAUD"]):
                print(line.strip()[:180])
                count += 1
    if count == 0:
        print("No matches found.")

search_june_23_symbols("logs/zohra_brain_a.log")
search_june_23_symbols("logs/zohra_engine_a.log")
