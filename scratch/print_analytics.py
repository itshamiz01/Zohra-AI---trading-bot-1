with open(r'c:\Users\dell\Desktop\trading_bot\zohra\api\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    if 'def analytics_full' in line:
        print(f"Found at line {i+1}: {line}")
        for j in range(30):
            print(f"  {i+1+j}: {lines[i+j]}")
