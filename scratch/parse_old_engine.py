import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Get zohra_engine.py content from baseline commit
content = subprocess.check_output(["git", "show", "f978915:zohra_engine.py"], encoding="utf-8")
lines = content.splitlines()

print("Functions in old zohra_engine.py:")
for i, l in enumerate(lines):
    if l.strip().startswith("def "):
        print(f"L{i+1}: {l.strip()}")

print("\nConstants in old zohra_engine.py:")
for i, l in enumerate(lines):
    if l.strip() and l.strip().split()[0].isupper() and "=" in l and not l.startswith(" "):
        print(f"L{i+1}: {l.strip()}")
