import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('zohra/api/dashboard.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

funcs = re.findall(r'function\s+([a-zA-Z0-9_]+)\s*\(', text)
print(f"Total functions in dashboard.html: {len(funcs)}")
print("Sample functions:", funcs[:30])

# Check where switchTab is defined
for i, line in enumerate(text.splitlines()):
    if 'function switchTab(' in line:
        print(f"switchTab found at line {i+1}")
    if 'function fetchDashboard(' in line:
        print(f"fetchDashboard found at line {i+1}")
    if 'function initDashboard(' in line:
        print(f"initDashboard found at line {i+1}")
