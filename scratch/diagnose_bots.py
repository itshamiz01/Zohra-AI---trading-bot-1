import sys
import os
import sqlite3
import json
import re

sys.stdout.reconfigure(encoding='utf-8')

bots = [
    ("Bot 1 (trading_bot - Trend)", r"C:\Users\dell\Desktop\trading_bot"),
    ("Bot 2 (Trading Bot 2.0 - Reversal)", r"C:\Users\dell\Desktop\Trading Bot 2.0"),
    ("Bot 3 (Trading Bot 3.0 - Breakout)", r"C:\Users\dell\Desktop\Trading Bot 3.0"),
]

for name, base_path in bots:
    print("=" * 80)
    print(f"DIAGNOSTIC REPORT FOR: {name}")
    print("=" * 80)
    
    # 1. Check Log file
    suffix = "a" if "Bot 1" in name else "b" if "Bot 2" in name else "c"
    log_file = os.path.join(base_path, "logs", f"zohra_brain_{suffix}.log")
    if not os.path.exists(log_file):
        log_file = os.path.join(base_path, "logs", "zohra_brain_a.log")
        
    print(f"Log file: {log_file}")
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    
    today_lines = [l for l in lines if "2026-09-01" in l]
    print(f"Total entries today: {len(today_lines)}")
    
    # Summary of decisions
    decisions = {}
    for l in today_lines:
        m = re.search(r"Regime=([A-Z_]+) \| Decision=([A-Z_]+)", l)
        if m:
            k = f"{m.group(1)} -> {m.group(2)}"
            decisions[k] = decisions.get(k, 0) + 1
    print("Decision Summary:", json.dumps(decisions, indent=2))
    
    # Find why setups were skipped/rejected today
    print("\n--- Key Reasons Setup Skipped / Rejected / Failed Today ---")
    reasons = []
    for l in today_lines:
        if any(k in l for k in [
            "Skipping setup", "REGIME_BLOCKED", "ORDER_CHECK_FAILED", 
            "Order failed", "Committee Veto", "Setup Rejected", 
            "Spread limit", "HIGH_CPU_LOAD", "Invalid stops"
        ]):
            reasons.append(l.strip())
    
    # Deduplicate and count
    reason_counts = {}
    for r in reasons:
        # clean timestamp
        cleaned = re.sub(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \w+\]\s*\[\w+\]\s*", "", r)
        reason_counts[cleaned] = reason_counts.get(cleaned, 0) + 1
        
    for rc, cnt in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  [{cnt}x] {rc}")
        
    # 2. Check SQLite Database
    db_file = os.path.join(base_path, "logs", f"zohra_trades_{suffix}.db")
    if not os.path.exists(db_file):
        db_file = os.path.join(base_path, "logs", "zohra_trades_a.db")
    print(f"\nDB file: {db_file}")
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cur.fetchall()]
    print(f"Tables: {tables}")
    for t in tables:
        cur.execute(f"SELECT count(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"  Table '{t}' has {cnt} rows")
        if any(k in t.lower() for k in ['open', 'active', 'position', 'trade']):
            cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 3")
            for r in cur.fetchall():
                print(f"    Sample row in {t}: {r}")
    conn.close()
    print("\n")
