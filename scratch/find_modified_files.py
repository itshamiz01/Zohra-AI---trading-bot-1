import os
import time
import sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

now = datetime.now()
three_days_ago = now - timedelta(days=3)

print(f"Current time: {now}")
print(f"Three days ago: {three_days_ago}")
print("\nFiles modified in the last 3 days:")

for root, dirs, files in os.walk('.'):
    # Skip virtual env and git folders
    if '.venv' in root or '.git' in root or '__pycache__' in root or '.vscode' in root:
        continue
    for file in files:
        path = os.path.join(root, file)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime > three_days_ago:
                print(f"  {path} | Modified: {mtime} | Size: {os.path.getsize(path)} bytes")
        except Exception as e:
            pass
