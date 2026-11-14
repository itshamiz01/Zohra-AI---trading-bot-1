#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — CROSS-BOT CORRELATION DIAGNOSTIC REPORT            ║
║     Analyzes signal logs from all bot instances to detect            ║
║     correlated trading behavior and measure independence.            ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python cross_bot_report.py [--log-dir PATH] [--lookback-hours N]

Reads signal snapshots from the shared cross-bot log directory and
produces a comprehensive correlation analysis report.
"""

import json
import os
import sys
import argparse
import datetime as dt
from collections import defaultdict
from pathlib import Path


def load_signals(log_dir: str, lookback_hours: int = 24) -> dict:
    """Load signal logs from all bots."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    bot_signals = defaultdict(list)

    for log_file in Path(log_dir).glob("signals_*.jsonl"):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        ts = entry.get("timestamp_utc", "")
                        entry_time = dt.datetime.fromisoformat(ts)
                        if entry_time.tzinfo is None:
                            entry_time = entry_time.replace(tzinfo=dt.timezone.utc)
                        if entry_time >= cutoff:
                            bot_signals[entry.get("bot_id", "unknown")].append(entry)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception as e:
            print(f"Error reading {log_file}: {e}")

    return bot_signals


def load_correlation_alerts(log_dir: str, lookback_hours: int = 24) -> list:
    """Load correlation alerts."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    alerts = []
    alert_file = os.path.join(log_dir, "correlation_alerts.jsonl")
    if os.path.exists(alert_file):
        try:
            with open(alert_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        ts = entry.get("timestamp_utc", "")
                        entry_time = dt.datetime.fromisoformat(ts)
                        if entry_time.tzinfo is None:
                            entry_time = entry_time.replace(tzinfo=dt.timezone.utc)
                        if entry_time >= cutoff:
                            alerts.append(entry)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception:
            pass
    return alerts


def analyze_correlation(bot_signals: dict) -> dict:
    """Compute cross-bot correlation metrics."""
    bot_ids = sorted(bot_signals.keys())
    if len(bot_ids) < 2:
        return {"error": "Need at least 2 bots with signal data for correlation analysis."}

    results = {
        "bot_ids": bot_ids,
        "signal_counts": {},
        "trade_counts": {},
        "pairwise": {},
        "strategy_correlation": defaultdict(int),
        "regime_agreement": 0,
        "regime_total": 0,
    }

    for bot_id in bot_ids:
        signals = bot_signals[bot_id]
        results["signal_counts"][bot_id] = len(signals)
        results["trade_counts"][bot_id] = sum(1 for s in signals if s.get("action") == "TRADE")

    # Pairwise correlation analysis
    for i, bot_a in enumerate(bot_ids):
        for bot_b in bot_ids[i + 1:]:
            pair_key = f"{bot_a} ↔ {bot_b}"
            signals_a = bot_signals[bot_a]
            signals_b = bot_signals[bot_b]

            # Match signals by candle time (within 60 seconds)
            same_direction = 0
            same_strategy = 0
            same_candle_trade = 0
            same_regime = 0
            compared = 0

            for sa in signals_a:
                ts_a = dt.datetime.fromisoformat(sa.get("timestamp_utc", ""))
                if ts_a.tzinfo is None:
                    ts_a = ts_a.replace(tzinfo=dt.timezone.utc)

                for sb in signals_b:
                    ts_b = dt.datetime.fromisoformat(sb.get("timestamp_utc", ""))
                    if ts_b.tzinfo is None:
                        ts_b = ts_b.replace(tzinfo=dt.timezone.utc)

                    if abs((ts_a - ts_b).total_seconds()) <= 60:
                        compared += 1
                        if sa.get("market_regime") == sb.get("market_regime"):
                            same_regime += 1
                        if sa.get("direction") == sb.get("direction") and sa.get("direction") != "NONE":
                            same_direction += 1
                        if sa.get("primary_strategy") == sb.get("primary_strategy") and sa.get("primary_strategy") != "NONE":
                            same_strategy += 1
                        if (sa.get("action") == "TRADE" and sb.get("action") == "TRADE" and
                                sa.get("direction") == sb.get("direction")):
                            same_candle_trade += 1
                        break  # Only match closest

            results["pairwise"][pair_key] = {
                "compared_signals": compared,
                "same_direction_rate": f"{same_direction / compared * 100:.1f}%" if compared else "N/A",
                "same_strategy_rate": f"{same_strategy / compared * 100:.1f}%" if compared else "N/A",
                "same_regime_rate": f"{same_regime / compared * 100:.1f}%" if compared else "N/A",
                "simultaneous_trade_count": same_candle_trade,
                "same_direction_count": same_direction,
            }

    return results


def print_report(bot_signals: dict, alerts: list, analysis: dict, lookback_hours: int):
    """Print formatted correlation report."""
    print("\n" + "=" * 72)
    print("  ZOHRA — CROSS-BOT SIGNAL CORRELATION REPORT")
    print("=" * 72)
    print(f"  Report Time: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Lookback:    {lookback_hours} hours")
    print(f"  Bots Found:  {len(analysis.get('bot_ids', []))}")
    print("=" * 72)

    if "error" in analysis:
        print(f"\n  ⚠️  {analysis['error']}")
        print("=" * 72)
        return

    # Signal counts per bot
    print("\n  📊 SIGNAL ACTIVITY")
    print("  " + "-" * 50)
    for bot_id in analysis["bot_ids"]:
        total = analysis["signal_counts"].get(bot_id, 0)
        trades = analysis["trade_counts"].get(bot_id, 0)
        print(f"    {bot_id:<20} Evaluations: {total:<6} Trades: {trades}")

    # Pairwise correlation
    print("\n  🔗 PAIRWISE CORRELATION")
    print("  " + "-" * 50)
    for pair_key, metrics in analysis.get("pairwise", {}).items():
        print(f"\n    {pair_key}")
        print(f"      Compared Signals:      {metrics['compared_signals']}")
        print(f"      Same Direction Rate:   {metrics['same_direction_rate']}")
        print(f"      Same Strategy Rate:    {metrics['same_strategy_rate']}")
        print(f"      Same Regime Rate:      {metrics['same_regime_rate']}")
        print(f"      Simultaneous Trades:   {metrics['simultaneous_trade_count']}")

        # Flag high correlation
        try:
            dir_rate = float(metrics['same_direction_rate'].rstrip('%'))
            if dir_rate >= 90:
                print(f"      ⚠️  CRITICAL: Extremely high correlation ({dir_rate:.0f}%)")
            elif dir_rate >= 70:
                print(f"      ⚠️  WARNING: High correlation ({dir_rate:.0f}%)")
        except (ValueError, AttributeError):
            pass

    # Correlation alerts
    if alerts:
        print(f"\n  🚨 CORRELATION ALERTS ({len(alerts)} in last {lookback_hours}h)")
        print("  " + "-" * 50)
        for alert in alerts[-10:]:  # Show last 10
            print(f"    [{alert.get('timestamp_utc', 'N/A')[:19]}]")
            print(f"      Trigger: {alert.get('triggering_bot', 'N/A')} → "
                  f"{alert.get('direction', 'N/A')} {alert.get('symbol', 'N/A')}")
            print(f"      Strategy: {alert.get('primary_strategy', 'N/A')}")
            print(f"      Correlated bots: {len(alert.get('correlated_bots', []))}")
            print(f"      Total exposure: {alert.get('total_exposure_multiplier', 'N/A')}x")
    else:
        print(f"\n  ✅ No correlation alerts in last {lookback_hours}h")

    # Independence assessment
    print("\n  📋 INDEPENDENCE ASSESSMENT")
    print("  " + "-" * 50)
    for pair_key, metrics in analysis.get("pairwise", {}).items():
        try:
            dir_rate = float(metrics['same_direction_rate'].rstrip('%'))
            independence = max(0, 100 - dir_rate)
            if independence < 20:
                verdict = "CRITICALLY CORRELATED"
            elif independence < 40:
                verdict = "HIGHLY CORRELATED"
            elif independence < 60:
                verdict = "MODERATELY CORRELATED"
            else:
                verdict = "REASONABLY INDEPENDENT"
            print(f"    {pair_key}: Independence = {independence:.0f}/100 → {verdict}")
        except (ValueError, AttributeError):
            print(f"    {pair_key}: Insufficient data")

    print("\n" + "=" * 72)
    print("  NOTE: This is a DIAGNOSTIC report. No trades were blocked.")
    print("=" * 72 + "\n")


def main():
    parser = argparse.ArgumentParser(description="ZOHRA Cross-Bot Correlation Report")
    parser.add_argument("--log-dir", type=str, default=None,
                        help="Path to shared cross-bot log directory")
    parser.add_argument("--lookback-hours", type=int, default=24,
                        help="Hours of history to analyze (default: 24)")
    args = parser.parse_args()

    # Auto-detect log directory
    if args.log_dir:
        log_dir = args.log_dir
    else:
        # Try common locations
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(script_dir, "logs", "cross_bot"),
            os.path.join(script_dir, "zohra", "logs", "cross_bot"),
        ]
        log_dir = None
        for c in candidates:
            if os.path.isdir(c):
                log_dir = c
                break
        if not log_dir:
            log_dir = candidates[0]

    if not os.path.isdir(log_dir):
        print(f"\n  ⚠️  Cross-bot log directory not found: {log_dir}")
        print("  Run bots with cross-bot monitoring enabled first.")
        print(f"  Or specify directory: python {sys.argv[0]} --log-dir /path/to/logs/cross_bot")
        return

    print(f"\n  Reading signals from: {log_dir}")

    bot_signals = load_signals(log_dir, args.lookback_hours)
    alerts = load_correlation_alerts(log_dir, args.lookback_hours)
    analysis = analyze_correlation(bot_signals)

    print_report(bot_signals, alerts, analysis, args.lookback_hours)


if __name__ == "__main__":
    main()
