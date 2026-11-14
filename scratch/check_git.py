import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

def run_git():
    try:
        status = subprocess.check_output(["git", "status"], stderr=subprocess.STDOUT, text=True)
        print("=== GIT STATUS ===")
        print(status)
    except Exception as e:
        print("Git status failed:", e)

    try:
        diff = subprocess.check_output(["git", "diff"], stderr=subprocess.STDOUT, text=True)
        print("=== GIT DIFF ===")
        print(diff[:2000]) # Limit output
    except Exception as e:
        print("Git diff failed:", e)

    try:
        log = subprocess.check_output(["git", "log", "-n", "10", "--oneline"], stderr=subprocess.STDOUT, text=True)
        print("=== GIT LOG ===")
        print(log)
    except Exception as e:
        print("Git log failed:", e)

run_git()
