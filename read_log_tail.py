import sys

log_path = r"C:\Users\dell\.gemini\antigravity\brain\8f1f64df-8211-43c4-a394-9e23094bc196\.system_generated\tasks\task-189.log"
sys.stdout.reconfigure(encoding='utf-8')

with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()
    print("TAIL OF TASK-189.LOG:")
    for line in lines[-150:]:
        print(line.strip())
