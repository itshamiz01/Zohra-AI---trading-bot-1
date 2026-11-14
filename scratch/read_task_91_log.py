import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

log_path = r"C:\Users\dell\.gemini\antigravity-ide\brain\7746d823-21b6-481f-88b8-dd990b6a899d\.system_generated\tasks\task-91.log"

if os.path.exists(log_path):
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        print(f.read())
else:
    print("Task 91 log not found yet.")
