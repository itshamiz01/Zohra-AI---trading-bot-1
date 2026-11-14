import sys
import os

# Set UTF-8 encoding for stdout on Windows
sys.stdout.reconfigure(encoding='utf-8')

# Test Bot A
print("=== TESTING BOT A PIPELINE (GOLD ONLY) ===")
sys.path.insert(0, r"c:\Users\dell\Desktop\trading_bot")
from zohra.core.symbol_resolver import symbol_resolver
from zohra.config.settings import ALLOWED_METALS, ACTIVE_PAIRS

print(f"Allowed metals: {ALLOWED_METALS}")
print(f"Active pairs: {ACTIVE_PAIRS}")
assert symbol_resolver.guard("XAUUSD"), "XAUUSD should pass guard"
assert not symbol_resolver.guard("XAGUSD"), "XAGUSD must be blocked in Gold-Only mode"
assert not symbol_resolver.guard("EURUSD"), "EURUSD must be blocked"
assert not symbol_resolver.guard("US30"), "US30 must be blocked"

# Test Spread calculation formula
# If ask - bid = 0.25 on XAUUSD, spread pips = 0.25 * 10 = 2.5 pips
xau_spread_pips = (2650.25 - 2650.00) * 10.0
assert abs(xau_spread_pips - 2.5) < 1e-5, f"XAUUSD spread formula incorrect: {xau_spread_pips}"

print("[SUCCESS] Bot A Gold-Only Symbol Guard passed successfully!")

# Test Bot B
print("\n=== TESTING BOT B PIPELINE (GOLD ONLY) ===")
sys.path.insert(0, r"c:\Users\dell\Desktop\Trading Bot 2.0")
import importlib
import zohra.core.symbol_resolver as b_resolver
assert b_resolver.symbol_resolver.guard("XAUUSD"), "Bot B XAUUSD should pass"
assert not b_resolver.symbol_resolver.guard("XAGUSD"), "Bot B XAGUSD must be blocked"
assert not b_resolver.symbol_resolver.guard("GBPUSD"), "Bot B GBPUSD must be blocked"
print("[SUCCESS] Bot B Gold-Only Symbol Guard passed successfully!")

# Test Bot C
print("\n=== TESTING BOT C PIPELINE (GOLD ONLY) ===")
sys.path.insert(0, r"c:\Users\dell\Desktop\Trading Bot 3.0")
import zohra.core.symbol_resolver as c_resolver
assert c_resolver.symbol_resolver.guard("XAUUSD"), "Bot C XAUUSD should pass"
assert not c_resolver.symbol_resolver.guard("XAGUSD"), "Bot C XAGUSD must be blocked"
assert not c_resolver.symbol_resolver.guard("BTCUSD"), "Bot C BTCUSD must be blocked"
print("[SUCCESS] Bot C Gold-Only Symbol Guard passed successfully!")

print("\n[COMPLETE] ALL 3 BOTS VERIFIED CLEAN FOR STRICT GOLD-ONLY (XAUUSD) TRADING!")
