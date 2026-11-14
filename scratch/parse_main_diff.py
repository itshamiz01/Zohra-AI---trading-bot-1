import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/git_diff.txt", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

def print_file_diff(filename):
    print(f"\nDIFF FOR {filename}:")
    in_diff = False
    for line in lines:
        if line.startswith(f"diff --git a/{filename}"):
            in_diff = True
            print(line.strip())
            continue
        elif line.startswith("diff --git a/") and in_diff:
            in_diff = False
        
        if in_diff:
            if (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---"):
                print(line.strip())

print_file_diff("main.py")
print_file_diff("scheduler.py")
