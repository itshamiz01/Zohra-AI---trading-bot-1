import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('zohra/api/dashboard.html', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines):
    l = line.strip()
    if any(k in l for k in ['<body', '<header', 'class="tabs-nav"', 'id="overview"', 'id="risk"', 'id="strategies"', 'id="playback"', 'id="chat"', '<script>']):
        print(f"Line {i+1}: {l[:110]}")
