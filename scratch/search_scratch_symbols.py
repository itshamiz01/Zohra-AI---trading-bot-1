import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Searching scratch/ for symbols...")
for file in os.listdir("scratch"):
    path = os.path.join("scratch", file)
    if os.path.isfile(path) and file.endswith(".py"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            for sym in ["EURAUD", "EURCAD", "GBPAUD"]:
                if sym in content:
                    print(f"  Found '{sym}' in {path}")
