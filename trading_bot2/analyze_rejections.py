"""
Zohra Rejection Analyzer
========================
View why trades were rejected and improve filters.

Usage:
    python analyze_rejections.py
"""

import json
from collections import Counter
from datetime import datetime

def load_rejections():
    try:
        with open("rejected_trades.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("No rejection log found. Run zohra_v5.py first.")
        return []

def analyze():
    rejections = load_rejections()

    if not rejections:
        return

    print("\n" + "=" * 70)
    print("ZOHRA v5 — REJECTION ANALYSIS")
    print("=" * 70)
    print(f"Total setups analyzed: {len(rejections)}")
    print(f"Period: {rejections[0]['timestamp'][:10]} to {rejections[-1]['timestamp'][:10]}")

    # Score distribution
    scores = [r['score'] for r in rejections]
    avg_score = sum(scores) / len(scores) if scores else 0
    print(f"\nAverage rejection score: {avg_score:.1f}/100")
    print(f"Highest rejected score: {max(scores) if scores else 0}")

    # Filter failure rates
    structure_fails = sum(1 for r in rejections if not r['structure'])
    liquidity_fails = sum(1 for r in rejections if not r['liquidity'])
    momentum_fails = sum(1 for r in rejections if not r['momentum'])
    volume_fails = sum(1 for r in rejections if not r['volume'])

    total = len(rejections)

    print("\n" + "-" * 70)
    print("FILTER FAILURE RATES:")
    print("-" * 70)
    print(f"Structure:  {structure_fails:4d}/{total} ({structure_fails/total*100:5.1f}%)")
    print(f"Liquidity:  {liquidity_fails:4d}/{total} ({liquidity_fails/total*100:5.1f}%)")
    print(f"Momentum:   {momentum_fails:4d}/{total} ({momentum_fails/total*100:5.1f}%)")
    print(f"Volume:     {volume_fails:4d}/{total} ({volume_fails/total*100:5.1f}%)")

    # Regime distribution
    regimes = Counter(r['regime'] for r in rejections)
    print("\n" + "-" * 70)
    print("REJECTIONS BY MARKET REGIME:")
    print("-" * 70)
    for regime, count in regimes.most_common():
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        print(f"{regime:12s}: {count:4d} ({pct:5.1f}%) {bar}")

    # Symbol distribution
    symbols = Counter(r['symbol'] for r in rejections)
    print("\n" + "-" * 70)
    print("REJECTIONS BY SYMBOL:")
    print("-" * 70)
    for symbol, count in symbols.most_common():
        pct = count / total * 100
        print(f"{symbol:8s}: {count:4d} ({pct:5.1f}%)")

    # Common reasons
    reasons = Counter(r['reason'] for r in rejections)
    print("\n" + "-" * 70)
    print("TOP 10 REJECTION REASONS:")
    print("-" * 70)
    for reason, count in reasons.most_common(10):
        print(f"{count:4d}x: {reason}")

    # Recommendations
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS:")
    print("=" * 70)

    worst_filter = max([
        ("Structure", structure_fails),
        ("Liquidity", liquidity_fails),
        ("Momentum", momentum_fails),
        ("Volume", volume_fails)
    ], key=lambda x: x[1])

    if worst_filter[1] / total > 0.5:
        print(f"⚠️  {worst_filter[0]} is rejecting {worst_filter[1]/total*100:.0f}% of setups.")
        print(f"   Consider if {worst_filter[0].lower()} threshold is too strict.")
    else:
        print("✅ Filters are well-balanced.")

    worst_regime = regimes.most_common(1)[0]
    if worst_regime[1] / total > 0.4:
        print(f"⚠️  {worst_regime[0]} regime accounts for {worst_regime[1]/total*100:.0f}% of rejections.")
        print(f"   Consider avoiding this regime entirely.")

    if avg_score > 85:
        print(f"⚠️  Average rejected score is {avg_score:.0f} — close to threshold.")
        print(f"   You may be missing good trades. Consider lowering threshold slightly.")
    elif avg_score < 50:
        print(f"✅ Average rejected score is {avg_score:.0f} — filters working well.")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    analyze()
