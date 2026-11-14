import sys
sys.stdout.reconfigure(encoding='utf-8')

def search_log(filepath, query):
    print(f"Searching for '{query}' in {filepath}...")
    count = 0
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f, 1):
            if query.lower() in line.lower():
                print(f"L{i}: {line.strip()}")
                count += 1
                if count >= 100:
                    print("Reached limit of 100 matches.")
                    break
    print(f"Search completed. Found {count} matches.")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "logs/zohra_engine_a.log"
    q = sys.argv[2] if len(sys.argv) > 2 else "starting"
    search_log(path, q)
