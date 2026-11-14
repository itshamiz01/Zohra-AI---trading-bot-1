import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

journal_path = "logs/decision_journal_a.jsonl"
print(f"Searching journal: {journal_path}")

target_times = ["15:51", "15:57", "15:59", "16:10"]

with open(journal_path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        try:
            data = json.loads(line)
            timestamp = data.get("timestamp", "")
            # check if timestamp contains any target times or if it's June 23
            if "2026-06-23" in timestamp:
                # check if any of target times in timestamp
                if any(t in timestamp for t in target_times):
                    print(f"\n--- Timestamp: {timestamp} ---")
                    print(f"Symbol: {data.get('symbol')} | Dir: {data.get('direction')} | Decision: {data.get('decision')}")
                    print(f"Strategy: {data.get('strategy')} | Score: {data.get('confidence_score')}")
                    print(f"Entry Price: {data.get('entry_price')} | SL: {data.get('stop_loss')} | TP: {data.get('take_profit')}")
                    rejection = data.get('rejection_reason')
                    if rejection:
                        print(f"Rejection: {rejection[:150]}...")
                    # print keys
                    print(f"Keys: {list(data.keys())}")
                    # let's look at the context or metadata if any
                    ctx = data.get("context_json", {})
                    if isinstance(ctx, str):
                        try:
                            ctx = json.loads(ctx)
                        except:
                            pass
                    print(f"Context keys: {list(ctx.keys()) if isinstance(ctx, dict) else type(ctx)}")
                    # print first 300 chars of context
                    print(f"Context snippet: {str(ctx)[:300]}")
        except Exception as e:
            print("Error parsing line:", e)
