import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for any occurrences of "modification" or related terms in logs
log_dir = "logs"
pattern = re.compile(r"modific|v3|precision|error|bug|fail|loss|regime|sizing", re.IGNORECASE)

print("=== LOG FILES AND SIZES ===")
for file in os.listdir(log_dir):
    path = os.path.join(log_dir, file)
    if os.path.isfile(path):
        print(f"File: {file} | Size: {os.path.getsize(path)} bytes")

# Let's inspect zohra_engine_a.log tail or search for version changes
print("\n=== SEARCHING LOGS ===")
for file in ["zohra_brain_a.log", "zohra_engine_a.log", "zohra_engine.log"]:
    path = os.path.join(log_dir, file)
    if os.path.exists(path):
        print(f"\nChecking {file}:")
        count = 0
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "version" in line.lower() or "upgrade" in line.lower() or "modification" in line.lower() or "restart" in line.lower() or "precision" in line.lower():
                    print(f"  {line.strip()[:150]}")
                    count += 1
                    if count > 20:
                        print("  [Truncated...]")
                        break
