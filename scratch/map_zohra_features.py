import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

zohra_dir = "zohra"

features = {}
for root, dirs, files in os.walk(zohra_dir):
    rel_root = os.path.relpath(root, zohra_dir)
    top_dir = rel_root.split(os.sep)[0] if rel_root != "." else "root"
    if top_dir not in features:
        features[top_dir] = []
    for f in files:
        if f.endswith(".py") and not f.startswith("__"):
            features[top_dir].append(os.path.join(rel_root, f))

for cat, flist in sorted(features.items()):
    print(f"\n--- {cat.upper()} ({len(flist)} files) ---")
    for f in flist[:12]:
        print(f"  {f}")
    if len(flist) > 12:
        print(f"  ... and {len(flist) - 12} more")
