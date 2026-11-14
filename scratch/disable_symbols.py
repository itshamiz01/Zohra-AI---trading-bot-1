import json
import os

filepath = "zohra/config/symbols.json"
if os.path.exists(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    allowed_symbols = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "NZDUSD", "XAUUSD"}
    
    for s in data["symbols"]:
        sym = s["symbol"]
        if sym in allowed_symbols:
            s["enabled"] = True
            print(f"Enabling {sym}")
        else:
            s["enabled"] = False
            print(f"Disabling {sym}")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("symbols.json updated successfully!")
else:
    print("symbols.json not found!")
