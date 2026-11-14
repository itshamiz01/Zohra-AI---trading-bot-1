import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Searching for SCALP_PAIRS:")
for root, dirs, files in os.walk('.'):
    if '.venv' in root or '.git' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for idx, line in enumerate(f):
                        if "SCALP_PAIRS" in line:
                            print(f"  {path}:{idx+1} | {line.strip()}")
            except Exception as e:
                pass
