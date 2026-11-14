import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("zohra.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

search_term = "VIRTUAL_EQUITY_OVERRIDE"
print(f"Searching for '{search_term}':")
for i, line in enumerate(lines):
    if search_term in line:
        print(f"Line {i+1}: {line.strip()}")
        # print surrounding lines
        start = max(0, i - 1)
        end = min(len(lines), i + 10)
        print("--- SURROUNDING LINES ---")
        for j in range(start, end):
            print(f"{j+1}: {lines[j].rstrip()}")
        print("-------------------------")
