import sys

sys.stdout.reconfigure(encoding='utf-8')

def search_log(path, term):
    print(f"\nSearching {path} for '{term}':")
    matches = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if term in line:
                print(line.strip())
                matches += 1
                if matches >= 100:
                    print("... Truncated (too many matches) ...")
                    break
    if matches == 0:
        print("No matches found.")

search_log("logs/zohra_brain_a.log", "2026-06-23 15:")
search_log("logs/zohra_brain_a.log", "2026-06-23 16:")
search_log("logs/zohra_engine_a.log", "2026-06-23 15:")
search_log("logs/zohra_engine_a.log", "2026-06-23 16:")
