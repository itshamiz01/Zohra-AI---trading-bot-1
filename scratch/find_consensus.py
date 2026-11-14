import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

search_dir = "."
for root, dirs, files in os.walk(search_dir):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "process_consensus_voting" in content:
                    print(f"Found in {path}")
            except Exception:
                pass
