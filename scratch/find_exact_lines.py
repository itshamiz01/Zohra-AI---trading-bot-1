import sys
sys.stdout.reconfigure(encoding='utf-8')

def find_lines_in_file(filepath, queries):
    print(f"\nSearching in {filepath}:")
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            for q in queries:
                if q in line:
                    print(f"  Line {idx+1}: {line.strip()}")
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")

find_lines_in_file("zohra/config/settings.py", ["HYBRID_SCALPER_MODE", "VIRTUAL_EQUITY_OVERRIDE", "MAX_OPEN_POSITIONS"])
find_lines_in_file("zohra/core/symbol_worker.py", ["HYBRID_SCALPER_MODE"])
find_lines_in_file("zohra/strategies/scalping_strategy.py", ["stop = min(entry - atr_val", "stop = max(entry + atr_val", "r >= 0.5", "DYNAMIC_TRAIL"])
