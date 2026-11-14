#!/usr/bin/env python3
"""
Zohra Multi-Agent Quantitative Engine Runner
Usage:
    python run_zohra.py             # Run in standard MT5 demo mode
    python run_zohra.py simulated   # Run in simulated offline mode
"""

import os
import sys
import warnings
# Suppress noisy library and deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning, message=".*generativeai.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Force UTF-8 encoding for stdout and stderr on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

# Load credentials from .env
load_dotenv()

# Inject path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zohra import ZohraEngine

def main():
    mode = "demo"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("simulated", "live", "demo"):
            mode = arg
        else:
            print(f"Unknown mode: {arg}. Available modes: demo, live, simulated")
            sys.exit(1)

    print("=" * 60)
    print(f"  ZOHRA QUANTITATIVE MULTI-AGENT ENGINE  |  MODE: {mode.upper()}")
    print("=" * 60)
    print("Press Ctrl+C to stop the engine loop gracefully.\n")

    engine = ZohraEngine(mode=mode)
    try:
        engine.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down gracefully...")
        engine.running = False
        print("✅ Shutdown complete.")

if __name__ == "__main__":
    main()
