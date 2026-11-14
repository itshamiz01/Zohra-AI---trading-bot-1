import os

folders = [
    r"C:\Users\dell\Desktop\trading_bot",
    r"C:\Users\dell\Desktop\Trading Bot 2.0",
    r"C:\Users\dell\Desktop\Trading Bot 3.0"
]

addition = '''

def load_bot_profile(role_or_id: Optional[str] = None) -> BotSpecializationProfile:
    """Loads bot profile by role or ID, defaulting to environment config."""
    if role_or_id:
        clean = str(role_or_id).upper().strip()
        if clean in SPECIALIZATION_PROFILES:
            return SPECIALIZATION_PROFILES[clean]
        for k, v in SPECIALIZATION_PROFILES.items():
            if k in clean or clean in k:
                return v
    return get_active_bot_profile()
'''

for folder in folders:
    prof_path = os.path.join(folder, "zohra", "config", "bot_profile.py")
    with open(prof_path, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()
    
    if "def load_bot_profile" not in code:
        code += addition
        with open(prof_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"Added load_bot_profile to {prof_path}")
    else:
        print(f"load_bot_profile already in {prof_path}")

print("Fix completed!")
