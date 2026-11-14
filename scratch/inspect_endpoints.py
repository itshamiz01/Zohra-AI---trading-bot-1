with open(r'c:\Users\dell\Desktop\trading_bot\zohra\api\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Let's find lines 1600 to 1700
lines = content.split('\n')
for i in range(1600, 1660):
    if i < len(lines):
        print(f"{i+1}: {lines[i]}")
