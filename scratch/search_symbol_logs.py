import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for EURAUD, EURCAD, GBPAUD in logs/zohra_brain_a.log and logs/zohra_engine_a.log
# We want to print all matching lines to see what was logged
def search_symbols_in_logs(path):
    print(f"\n==========================================")
    print(f"File: {path}")
    print(f"==========================================")
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if any(sym in line for sym in ["EURAUD", "EURCAD", "GBPAUD"]):
                print(line.strip()[:180])
                count += 1
                if count >= 100:
                    print("... Truncated (too many matches) ...")
                    break
    if count == 0:
        print("No matches found.")

search_symbols_in_logs("logs/zohra_brain_a.log")
search_symbols_in_logs("logs/zohra_engine_a.log")
