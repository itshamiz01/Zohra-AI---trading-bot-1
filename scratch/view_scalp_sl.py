import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("zohra/strategies/scalping_strategy.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

print("Signal generation details in scalping_strategy.py (generate_signal):")
in_gen_sig = False
start_line = 0
for idx, l in enumerate(lines):
    if "def generate_signal" in l:
        in_gen_sig = True
        start_line = idx
        print(f"generate_signal starts at line {idx+1}")
    if in_gen_sig and "def check_exit" in l:
        print(f"generate_signal ends at line {idx}")
        in_gen_sig = False
        end_line = idx
        break

# Let's print lines within generate_signal that contain sl, stop, target, tp
for idx in range(start_line, end_line):
    line = lines[idx]
    if any(k in line.lower() for k in ["sl", "stop", "tp", "target", "exit"]):
        print(f"L{idx+1}: {line.strip()}")
