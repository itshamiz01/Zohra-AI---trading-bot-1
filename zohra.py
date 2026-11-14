#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║               ZOHRA UNIFIED TRADING OPERATING SYSTEM             ║
║               Runs All 3 MT5 Accounts Concurrently               ║
║                                                                  ║
║  15 Strategies │ Centralized Intelligence │ Isolated Execution   ║
║                                                                  ║
║  Usage:                                                          ║
║    python zohra.py                                               ║
║    python zohra.py --accounts account_01 account_02              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import asyncio
import argparse

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_zohra_unified import run_unified


def main():
    parser = argparse.ArgumentParser(
        description="ZOHRA Unified Trading System — Run All 3 Accounts"
    )
    parser.add_argument(
        '--accounts', nargs='*', default=None,
        help="Optional: Specific accounts to run (defaults to all active accounts)"
    )
    args = parser.parse_args()

    print("=" * 62)
    print("  🚀 STARTING ZOHRA UNIFIED TRADING SYSTEM (ALL ACCOUNTS)")
    print("=" * 62)

    try:
        asyncio.run(run_unified(account_ids=args.accounts))
    except KeyboardInterrupt:
        print("\n🛑 ZOHRA shutdown complete.")


if __name__ == "__main__":
    main()
