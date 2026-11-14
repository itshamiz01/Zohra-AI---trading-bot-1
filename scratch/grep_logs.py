import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

keywords = ["setup_detection", "outcome_analysis", "orchestrator", "pattern_database"]
with open("logs/zohra_brain_a.log", "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if any(kw in line.lower() for kw in keywords):
            try:
                print(line.strip())
            except Exception:
                print(line.encode('ascii', errors='replace').decode('ascii').strip())
