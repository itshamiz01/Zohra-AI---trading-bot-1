#!/usr/bin/env python3
"""
Zohra Multi-Agent Quantitative Engine Entry Point
==================================================
Runs the complete multi-agent Forex and Gold trading loop.
Supports live, demo, and simulated broker modes.
"""

import os
import sys
import importlib.util
import warnings
# Suppress noisy library and deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning, message=".*generativeai.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from dotenv import load_dotenv

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

# Load credentials from .env
load_dotenv()

# Inject path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load zohra.py supreme orchestrator explicitly
spec = importlib.util.spec_from_file_location("zohra_brain", os.path.join(os.path.dirname(os.path.abspath(__file__)), "zohra.py"))
zohra_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zohra_module)
ZohraBrain = zohra_module.ZohraBrain

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Zohra Multi-Agent Quantitative Trading Engine")
    parser.add_argument('mode', type=str, nargs='?', default='demo', choices=['demo', 'live', 'simulated'],
                        help="Execution mode: demo (default), live, or simulated")
    parser.add_argument('--min-score', type=int, default=65,
                        help="Minimum signal score threshold (default: 65)")
    args = parser.parse_args()

    engine = ZohraBrain(
        mode=args.mode,
        min_score=args.min_score
    )

    try:
        engine.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down Zohra Brain gracefully...")
        engine.running = False
        print("✅ Shutdown complete.")

if __name__ == "__main__":
    main()
