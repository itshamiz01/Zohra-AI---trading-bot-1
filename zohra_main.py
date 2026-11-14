#!/usr/bin/env python3
"""
Zohra Trading Engine — Production Entry Point
==============================================
Usage:
    python zohra_main.py status          # Account + analytics snapshot
    python zohra_main.py report daily    # Generate daily report
    python zohra_main.py report weekly
    python zohra_main.py report monthly
    python zohra_main.py api             # Start REST API server
    python zohra_main.py rejections      # Analyze rejected setups
"""

import sys
import warnings
# Suppress noisy library and deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning, message=".*generativeai.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from dotenv import load_dotenv

load_dotenv()


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "status"

    if cmd == "api":
        try:
            import uvicorn
            from zohra.api.app import app
            from zohra.config.settings import settings
            uvicorn.run(app, host=settings.api_host, port=settings.api_port)
        except ImportError:
            print("Install API deps: pip install fastapi uvicorn")
        return

    if cmd == "rejections":
        from zohra.tools.analyze_rejections import analyze
        analyze()
        return

    if cmd == "report":
        period = args[1] if len(args) > 1 else "daily"
        from zohra.reporting.report_generator import ReportGenerator
        report = ReportGenerator().generate(period)
        print(report["summary_text"])
        print(f"Report saved: {report['paths']['html']}")
        return

    if cmd == "status":
        import os
        import importlib.util
        spec = importlib.util.spec_from_file_location("zohra_brain", os.path.join(os.path.dirname(os.path.abspath(__file__)), "zohra.py"))
        zohra_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(zohra_module)
        ZohraBrain = zohra_module.ZohraBrain

        engine = ZohraBrain()
        if engine.start(run_loop=False):
            status = engine.get_status()
            print(f"Broker: MT5 | Balance: {status['account'].get('balance', 'N/A')}")
            print(f"Open positions: {status['open_positions']}")
            daily = status["analytics_daily"]
            print(f"Today: {daily.get('total_trades', 0)} trades | "
                  f"Win rate: {daily.get('win_rate_pct', 0)}% | "
                  f"Net P&L: ${daily.get('net_pnl', 0)}")
            engine.stop()
        else:
            print("Failed to connect to MT5. Ensure terminal is running.")
        return

    print(__doc__)


if __name__ == "__main__":
    main()
