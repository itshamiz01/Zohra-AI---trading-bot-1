import sys
import os
import re

sys.stdout.reconfigure(encoding='utf-8')

app_path = "zohra/api/app.py"

routes = []
with open(app_path, "r", encoding="utf-8", errors="ignore") as f:
    for line_num, line in enumerate(f, 1):
        m = re.search(r"@app\.(get|post|put|delete|websocket)\([\"']([^\"']+)[\"']", line)
        if m:
            routes.append((m.group(1).upper(), m.group(2), line_num))

print(f"Total FastAPI routes directly defined in app.py: {len(routes)}")
for method, path, lnum in routes:
    print(f"  [{method}] {path} (line {lnum})")

with open(app_path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()
routers = re.findall(r"include_router\(([^,\)]+)", text)
print(f"\nIncluded Routers ({len(routers)}): {routers}")
