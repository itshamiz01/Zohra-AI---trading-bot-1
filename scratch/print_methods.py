import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    content = f.read()

import re
matches = re.findall(r"^\s*def\s+(\w+)\(", content, re.MULTILINE)
print("=== Methods in zohra.py ===")
for m in matches:
    print(m)
