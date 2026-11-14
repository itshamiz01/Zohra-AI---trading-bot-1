import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/git_diff.txt", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

in_settings_diff = False
settings_diff = []

for line in lines:
    if line.startswith("diff --git a/zohra/config/settings.py"):
        in_settings_diff = True
        settings_diff.append(line)
        continue
    elif line.startswith("diff --git a/") and in_settings_diff:
        in_settings_diff = False
    
    if in_settings_diff:
        settings_diff.append(line)

print("".join(settings_diff))
