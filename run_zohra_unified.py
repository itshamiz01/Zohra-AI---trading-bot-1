#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║        ZOHRA UNIFIED TRADING SYSTEM — Entry Point                ║
║                                                                  ║
║  One bot, 3 MT5 accounts, 15 strategies, centralized intelligence║
║                                                                  ║
║  Usage:                                                          ║
║    python run_zohra_unified.py                   # Run all       ║
║    python run_zohra_unified.py --accounts 1 2    # Specific accts║
║    python run_zohra_unified.py --status          # System status ║
║    python run_zohra_unified.py --kill global     # Emergency stop║
╚══════════════════════════════════════════════════════════════════╝

Architecture:
  ZOHRA OS
  │
  ┌──────▼──────┐
  │  Supervisor  │   ← Process lifecycle management
  └──────┬──────┘
         │
  ┌──────┼──────────────────┬───────────────────┐
  │      │                  │                   │
  ▼      ▼                  ▼                   ▼
  Market Data    Strategy Engine      Risk & Decision Engine
  Service        (15 Strategies)
  │                  │                       │
  │              Signal Bus                  │
  │                  │                       │
  │      ┌───────────┼───────────┐           │
  │      │           │           │           │
  ▼      ▼           ▼           ▼           │
  ACCT-01      ACCT-02      ACCT-03          │
  Worker       Worker       Worker           │
  │            │            │                │
  MT5 #1       MT5 #2       MT5 #3           │
  │            │            │                │
  └────────────┼────────────┘                │
               ▼                             │
        Trade Event Bus ◄────────────────────┘
               │
  ┌────────────┼────────────┐
  ▼            ▼            ▼
  Journal   Analytics    Memory
"""

import os
import sys
import asyncio
import warnings
import argparse
import signal as os_signal

# Suppress noisy library and deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning, message=".*generativeai.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Force UTF-8 encoding for stdout and stderr on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

# Inject path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

# ─── Logging Setup ───
from zohra.config.settings import LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s UTC] [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(LOG_DIR, "zohra_unified.log"),
            encoding='utf-8'
        ),
    ]
)

logger = logging.getLogger("zohra.unified")


async def run_unified(account_ids=None):
    """Run the ZOHRA unified trading system."""
    from zohra.engines.supervisor import ZohraSupervisor

    supervisor = ZohraSupervisor(account_ids=account_ids)

    # Handle graceful shutdown
    loop = asyncio.get_running_loop()

    def handle_shutdown():
        logger.info("\n🛑 Shutdown signal received...")
        asyncio.create_task(supervisor.shutdown())

    # Register signal handlers for graceful shutdown
    try:
        loop.add_signal_handler(os_signal.SIGINT, handle_shutdown)
        loop.add_signal_handler(os_signal.SIGTERM, handle_shutdown)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler in all cases
        pass

    try:
        await supervisor.start()
    except KeyboardInterrupt:
        logger.info("\n🛑 Keyboard interrupt — shutting down...")
        await supervisor.shutdown()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        await supervisor.shutdown()


def main():
    parser = argparse.ArgumentParser(
        description="ZOHRA Unified Trading System — One bot, 3 MT5 accounts, 15 strategies"
    )
    parser.add_argument(
        '--accounts', nargs='*', default=None,
        help="Specific account IDs to run (e.g., --accounts account_01 account_02). "
             "If not specified, all active accounts are used."
    )
    parser.add_argument(
        '--status', action='store_true',
        help="Print system configuration and exit"
    )
    parser.add_argument(
        '--kill', choices=['global', 'account', 'strategy'],
        help="Activate kill switch"
    )
    parser.add_argument(
        '--kill-target', default=None,
        help="Target for account/strategy kill switch"
    )

    args = parser.parse_args()

    # ─── Status Mode ───
    if args.status:
        from zohra.config.settings import ACCOUNT_CONFIGS, ACTIVE_ACCOUNT_CONFIGS
        print("=" * 60)
        print("  ZOHRA UNIFIED SYSTEM — Configuration Status")
        print("=" * 60)
        for config in ACCOUNT_CONFIGS:
            status = "✅ ACTIVE" if config.enabled else "⚠️ INACTIVE"
            print(f"\n  {config.account_id}: {config.name}")
            print(f"    Login:    {config.login}")
            print(f"    Server:   {config.server}")
            print(f"    Terminal: {config.terminal_path}")
            print(f"    Status:   {status}")
        print(f"\n  Active accounts: {len(ACTIVE_ACCOUNT_CONFIGS)}/{len(ACCOUNT_CONFIGS)}")
        print("=" * 60)
        return

    # ─── Kill Switch Mode ───
    if args.kill:
        print(f"🛑 Kill switch: {args.kill} (target: {args.kill_target or 'all'})")
        # This would need a running system to send the kill switch to
        # For now, just print the command
        print("Kill switch commands are handled within the running system.")
        print("Use the API or Telegram bot to activate kill switches at runtime.")
        return

    # ─── Normal Startup ───
    print("=" * 60)
    print("  ZOHRA UNIFIED TRADING OPERATING SYSTEM")
    print("  One Bot │ 3 MT5 Accounts │ 15 Strategies │ Centralized Intelligence")
    print("=" * 60)
    print("  Press Ctrl+C to shut down gracefully.\n")

    account_ids = args.accounts if args.accounts else None

    try:
        asyncio.run(run_unified(account_ids=account_ids))
    except KeyboardInterrupt:
        print("\n🛑 Shutdown complete.")


if __name__ == "__main__":
    main()
