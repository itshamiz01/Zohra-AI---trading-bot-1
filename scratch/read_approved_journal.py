import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

journal_path = "logs/decision_journal_a.jsonl"
print(f"Reading all APPROVED entries in journal: {journal_path}")

with open(journal_path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("decision") == "APPROVED":
                timestamp = data.get("timestamp", "")
                if "2026-06-2" in timestamp: # June 20-29
                    print(f"Time: {timestamp} | Symbol: {data.get('symbol')} | Dir: {data.get('direction')} | Strat: {data.get('strategy')} | Entry Price: {data.get('entry_price')} | SL: {data.get('stop_loss')} | TP: {data.get('take_profit')}")
        except Exception as e:
            pass
