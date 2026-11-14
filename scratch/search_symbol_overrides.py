import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Searching codebase for occurrences of symbol overrides or hardcoded 'EURUSD'...")
pattern = re.compile(r"symbol\s*=\s*['\"]EURUSD['\"]", re.IGNORECASE)

for root, dirs, files in os.walk('.'):
    if '.venv' in root or '.git' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        if pattern.search(line):
                            print(f"  {path}:{i} | {line.strip()}")
            except:
                pass
