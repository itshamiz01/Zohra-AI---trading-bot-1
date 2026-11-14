import os
import json

folders = [
    r"C:\Users\dell\Desktop\trading_bot",
    r"C:\Users\dell\Desktop\Trading Bot 2.0",
    r"C:\Users\dell\Desktop\Trading Bot 3.0"
]

# 1. Reset stale active_portfolio_state.json across all folders
for folder in folders:
    cross_bot_dir = os.path.join(folder, "logs", "cross_bot")
    os.makedirs(cross_bot_dir, exist_ok=True)
    state_file = os.path.join(cross_bot_dir, "active_portfolio_state.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump({"active_positions": {}, "last_updated": ""}, f, indent=2)
    print(f"Reset {state_file}")

# 2. Update investment_committee.py in all folders
for folder in folders:
    comm_path = os.path.join(folder, "zohra", "core", "investment_committee.py")
    if os.path.exists(comm_path):
        with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
            
        old_target = """        # Decide trade grade
        if final_score >= 90:
            grade = "A+"
            action = "EXECUTE"
            position_mult = 1.00
        elif final_score >= 80:
            grade = "A"
            action = "EXECUTE"
            position_mult = 0.75
        elif final_score >= 70:
            grade = "B"
            action = "EXECUTE"
            position_mult = 0.50
        elif final_score >= 60:
            grade = "C"
            action = "OPTIONAL"
            position_mult = 0.25
        else:
            grade = "REJECT"
            action = "REJECT"
            position_mult = 0.00
            
        if final_score < 70:
            action = "REJECT"
            position_mult = 0.00"""

        new_target = """        from zohra.config.settings import ALLOW_C_SETUPS

        # Decide trade grade
        if final_score >= 90:
            grade = "A+"
            action = "EXECUTE"
            position_mult = 1.00
        elif final_score >= 80:
            grade = "A"
            action = "EXECUTE"
            position_mult = 0.75
        elif final_score >= 70:
            grade = "B"
            action = "EXECUTE"
            position_mult = 0.50
        elif final_score >= 60 and ALLOW_C_SETUPS:
            grade = "C"
            action = "EXECUTE"
            position_mult = 0.25
        else:
            grade = "REJECT"
            action = "REJECT"
            position_mult = 0.00"""

        if old_target in code:
            code = code.replace(old_target, new_target)
            with open(comm_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"Fixed investment_committee.py in {folder}")
        else:
            print(f"Target block not found in {comm_path}")

# 3. Update portfolio_risk_coordinator.py in all folders
for folder in folders:
    coord_path = os.path.join(folder, "zohra", "core", "portfolio_risk_coordinator.py")
    if os.path.exists(coord_path):
        with open(coord_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # Add auto-cleanup of stale positions in _load_fleet_state
        old_load = """    def _load_fleet_state(self) -> Dict[str, Any]:
        \"\"\"Loads aggregate position state across all 3 bot instances.\"\"\"
        if not os.path.exists(self.state_file):
            return {"active_positions": {}, "last_updated": ""}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"active_positions": {}, "last_updated": ""}"""

        new_load = """    def _load_fleet_state(self) -> Dict[str, Any]:
        \"\"\"Loads aggregate position state across all 3 bot instances and purges stale entries.\"\"\"
        if not os.path.exists(self.state_file):
            return {"active_positions": {}, "last_updated": ""}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Reconcile / purge entries older than 2 hours or invalid
            active = data.get("active_positions", {})
            now = dt.datetime.now(dt.timezone.utc)
            valid_active = {}
            for k, v in active.items():
                try:
                    opened_str = v.get("opened_at", "")
                    if opened_str:
                        op_dt = dt.datetime.fromisoformat(opened_str.replace("Z", "+00:00"))
                        if (now - op_dt).total_seconds() > 7200: # 2 hours max lifetime
                            continue
                    valid_active[k] = v
                except Exception:
                    continue
            if len(valid_active) != len(active):
                data["active_positions"] = valid_active
                self._save_fleet_state(data)
            return data
        except Exception:
            return {"active_positions": {}, "last_updated": ""}"""

        if old_load in code:
            code = code.replace(old_load, new_load)
            with open(coord_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"Fixed portfolio_risk_coordinator.py in {folder}")

print("All fixes successfully applied!")
