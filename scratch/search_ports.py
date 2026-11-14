with open(r'c:\Users\dell\Desktop\trading_bot\zohra\api\dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    if '8000' in line:
        print(f"Line {i+1}: {line.strip()}")
