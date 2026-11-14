#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║               ZOHRA — ACCOUNT 2 EXCLUSIVE RUNNER                 ║
║               Runs Account 2 with all 15 Strategies              ║
║                                                                  ║
║  Account:  account_02 (Secondary)                                ║
║  Terminal: C:\\MetaTrader 5 B\\terminal64.exe                     ║
║                                                                  ║
║  Usage:                                                          ║
║    python zohra2.py                                              ║
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
    print("  🚀 STARTING ZOHRA — ACCOUNT 2 ONLY")
    print("  Terminal: C:\\MetaTrader 5 B\\terminal64.exe")
    print("=" * 62)

    try:
        asyncio.run(run_unified(account_ids=['account_02']))
    except KeyboardInterrupt:
        print("\n🛑 ZOHRA Account 2 shutdown complete.")


if __name__ == "__main__":
    main()
