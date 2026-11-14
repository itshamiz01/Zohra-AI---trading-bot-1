import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for engine startup messages in both logs/zohra_engine_a.log and zohra/logs/zohra_engine.log
def check_startups(filepath):
    print(f"\n--- Startup messages in {filepath} ---")
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if "Starting Zohra Engine" in line or "Zohra Engine started" in line or "Starting Zohra central brain" in line:
                print(line.strip())

check_startups("logs/zohra_engine_a.log")
check_startups("zohra/logs/zohra_engine.log")
