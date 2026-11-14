import subprocess
import sys

try:
    diff = subprocess.check_output(["git", "diff"], stderr=subprocess.STDOUT)
    with open("scratch/git_diff.txt", "wb") as f:
        f.write(diff)
    print("Git diff written to scratch/git_diff.txt successfully.")
except Exception as e:
    print("Failed to run git diff:", e)
