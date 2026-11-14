import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

try:
    log_stat = subprocess.check_output(["git", "log", "--stat"], text=True, errors="ignore")
    print("=== GIT LOG STAT ===")
    print(log_stat[:4000])
except Exception as e:
    print("Failed to run git log --stat:", e)
