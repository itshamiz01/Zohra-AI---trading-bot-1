#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║               ZOHRA UNIFIED SYSTEM STATUS DASHBOARD              ║
║               Displays Current Configuration & State             ║
║                                                                  ║
║  Usage:                                                          ║
║    python zohrastatus.py                                         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zohra.config.settings import ACCOUNT_CONFIGS, ACTIVE_ACCOUNT_CONFIGS, ACTIVE_PAIRS
from zohra.config.bot_profile import ZOHRA_UNIFIED_PROFILE


def main():
    print("=" * 66)
    print("  📊 ZOHRA UNIFIED TRADING SYSTEM — CONFIGURATION STATUS")
    print("=" * 66)

    # 1. Accounts
    print("\n  [MT5 ACCOUNTS CONFIGURED]")
    for i, config in enumerate(ACCOUNT_CONFIGS, 1):
        term_exists = os.path.exists(config.terminal_path)
        term_indicator = "✅ Terminal Found" if term_exists else "❌ Terminal Missing"
        status_icon = "✅ ACTIVE" if config.enabled else "⚠️ INACTIVE"

        print(f"  ┌─ Account {i}: {config.name}")
        print(f"  │  ID:       {config.account_id}")
        print(f"  │  Login:    {config.login}")
        print(f"  │  Server:   {config.server}")
        print(f"  │  Terminal: {config.terminal_path} ({term_indicator})")
        print(f"  │  Magic:    {config.magic_offset} (base: 202401)")
        print(f"  └─ Status:   {status_icon}")
        print()

    print(f"  Summary: {len(ACTIVE_ACCOUNT_CONFIGS)} of {len(ACCOUNT_CONFIGS)} accounts active.")

    # 2. Redis Message Bus
    print("\n  [INTER-PROCESS MESSAGE BUS]")
    try:
        import redis
        r = redis.Redis(protocol=2, socket_connect_timeout=1)
        if r.ping():
            print("  Status:     ✅ ONLINE (Redis RESP2 transport active)")
            print("  Isolation:  Each account runs in an independent OS subprocess")
        else:
            print("  Status:     ⚠️ Redis ping failed (in-memory mode)")
    except Exception as e:
        print(f"  Status:     ⚠️ In-Memory Mode ({e})")

    # 3. Strategy Engine
    print("\n  [STRATEGY ENGINE — ALL 15 STRATEGIES]")
    for j, strat in enumerate(ZOHRA_UNIFIED_PROFILE.enabled_strategies, 1):
        print(f"   {j:2d}. {strat}")

    # 4. Traded Symbols
    print(f"\n  [TRADED SYMBOLS]: {', '.join(ACTIVE_PAIRS)}")

    # 5. Quick Launch Guide
    print("\n" + "=" * 66)
    print("  ⚡ QUICK RUN COMMANDS:")
    print("  • Run all 3 accounts:     python zohra.py")
    print("  • Run Account 1 only:     python zohra1.py")
    print("  • Run Account 2 only:     python zohra2.py")
    print("  • Run Account 3 only:     python zohra3.py")
    print("  • Run system test:        python zohratest.py")
    print("  • Check status anytime:   python zohrastatus.py")
    print("=" * 66)


if __name__ == "__main__":
    main()
