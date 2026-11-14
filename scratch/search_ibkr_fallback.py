import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

search_term = "ibkr"
for root, dirs, files in os.walk("."):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if search_term in line.lower():
                            print(f"{path} Line {i+1}: {line.strip()}")
            except Exception:
                pass
