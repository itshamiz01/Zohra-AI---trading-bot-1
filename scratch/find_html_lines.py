with open(r'c:\Users\dell\Desktop\trading_bot\zohra\api\dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    if 'async function fetchDashboard()' in line:
        print(f"fetchDashboard found at line {i+1}")
    if 'function connectWebSocket()' in line:
        print(f"connectWebSocket found at line {i+1}")
    if 'let closedTrades = [];' in line:
        print(f"closedTrades found at line {i+1}")
