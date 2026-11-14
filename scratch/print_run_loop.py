import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    content = f.read()

import re
match = re.search(r"^\s*def _run_loop\(", content, re.MULTILINE)
if match:
    # Find start line
    idx = content.count("\n", 0, match.start())
    lines = content.splitlines()
    print("=== _run_loop in zohra.py ===")
    for i in range(idx, min(idx + 120, len(lines))):
        print(f"{i+1}: {lines[i]}")
else:
    print("Method _run_loop not found")
