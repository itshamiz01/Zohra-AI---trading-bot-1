import os

folders = [
    r"C:\Users\dell\Desktop\trading_bot",
    r"C:\Users\dell\Desktop\Trading Bot 2.0",
    r"C:\Users\dell\Desktop\Trading Bot 3.0"
]

for folder in folders:
    print(f"Fixing {folder}...")
    
    # 1. Fix zohra.py (NameError: symbol_info)
    zohra_path = os.path.join(folder, "zohra.py")
    if os.path.exists(zohra_path):
        with open(zohra_path, "r", encoding="utf-8", errors="ignore") as f:
            z_code = f.read()
        
        target = """            # Snap lots to steps and limits for safety
            if symbol_info:"""
            
        replacement = """            # Snap lots to steps and limits for safety
            symbol_info = await asyncio.to_thread(mt5_broker.get_symbol_info, symbol)
            if symbol_info:"""
            
        if target in z_code:
            z_code = z_code.replace(target, replacement)
            with open(zohra_path, "w", encoding="utf-8") as f:
                f.write(z_code)
            print(f"  Fixed symbol_info in {zohra_path}")
        else:
            print(f"  Target not found in {zohra_path}")
            
    # 2. Fix settings.py (MAX_SECTOR_POSITIONS Forex: 0 -> 5)
    settings_path = os.path.join(folder, "zohra", "config", "settings.py")
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8", errors="ignore") as f:
            s_code = f.read()
            
        target_sector = """MAX_SECTOR_POSITIONS = {
    "Forex": 0,
    "Metals": 5,
    "Indices": 0
}"""

        replacement_sector = """MAX_SECTOR_POSITIONS = {
    "Forex": 5,
    "Metals": 5,
    "Indices": 5
}"""

        if target_sector in s_code:
            s_code = s_code.replace(target_sector, replacement_sector)
            with open(settings_path, "w", encoding="utf-8") as f:
                f.write(s_code)
            print(f"  Fixed MAX_SECTOR_POSITIONS in {settings_path}")
        else:
            # try regex or simple replace
            s_code = s_code.replace('"Forex": 0,', '"Forex": 5,').replace('"Indices": 0', '"Indices": 5')
            with open(settings_path, "w", encoding="utf-8") as f:
                f.write(s_code)
            print(f"  Replaced Forex limit in {settings_path}")

print("All fixes applied!")
