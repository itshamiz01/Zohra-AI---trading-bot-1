import sys

sys.stdout.reconfigure(encoding='utf-8')

log_file = "logs/zohra_brain_a.log"
print(f"Searching June 24 logs in: {log_file}")

with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "2026-06-24" in line:
            # print all lines related to order placement or execution
            if any(x in line for x in ["placed", "Zohra", "TRADE", "ORDER", "order", "Buy", "Sell", "execution", "execute"]):
                print(line.strip()[:180])
