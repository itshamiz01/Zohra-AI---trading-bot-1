#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║               ZOHRA — ACCOUNT 3 EXCLUSIVE RUNNER                 ║
║               Runs Account 3 with all 15 Strategies              ║
║                                                                  ║
║  Account:  account_03 (Tertiary)                                 ║
║  Terminal: C:\\MetaTrader 5 C\\terminal64.exe                     ║
║                                                                  ║
║  Usage:                                                          ║
║    python zohra3.py                                              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import asyncio

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_zohra_unified import run_unified


def main():
    print("=" * 62)
    print("  🚀 STARTING ZOHRA — ACCOUNT 3 ONLY")
    print("  Terminal: C:\\MetaTrader 5 C\\terminal64.exe")
    print("=" * 62)

    try:
        asyncio.run(run_unified(account_ids=['account_03']))
    except KeyboardInterrupt:
        print("\n🛑 ZOHRA Account 3 shutdown complete.")


if __name__ == "__main__":
    main()
