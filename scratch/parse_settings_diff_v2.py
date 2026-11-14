import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/git_diff.txt", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

in_settings_diff = False
changes = []

for line in lines:
    if line.startswith("diff --git a/zohra/config/settings.py"):
        in_settings_diff = True
        changes.append(line)
        continue
    elif line.startswith("diff --git a/") and in_settings_diff:
        in_settings_diff = False
    
    if in_settings_diff:
        if (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---"):
            changes.append(line)

with open("scratch/settings_diff_only.txt", "w", encoding="utf-8") as f:
    f.writelines(changes)

print("Settings diff size:", len(changes))
