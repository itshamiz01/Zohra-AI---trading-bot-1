"""
Rejection analytics CLI — reads from SQLite rejected_trades table.
Replaces trading_bot2 JSON-only analyzer with database-backed version.
"""

import argparse
from collections import Counter

from zohra.db.repositories.rejections import RejectionRepository


def analyze(limit: int = 5000):
    repo = RejectionRepository()
    rejections = repo.get_recent(limit=limit)

    if not rejections:
        print("No rejection records found.")
        return

    total = len(rejections)
    print("\n" + "=" * 70)
    print("ZOHRA — REJECTION ANALYSIS (Database)")
    print("=" * 70)
    print(f"Total rejected setups: {total}")

    scores = [r["confidence_score"] for r in rejections]
    print(f"Average score: {sum(scores)/len(scores):.1f}")
    print(f"Highest rejected score: {max(scores)}")

    # Flatten failed conditions
    all_failed = []
    for r in rejections:
        fc = r.get("failed_conditions") or []
        if isinstance(fc, list):
            all_failed.extend(fc)

    print("\nFILTER FAILURE RATES:")
    for cond, count in Counter(all_failed).most_common():
        print(f"  {cond:20s}: {count:4d} ({count/total*100:5.1f}%)")

    print("\nBY REGIME:")
    for regime, count in Counter(r.get("market_regime") or "unknown" for r in rejections).most_common():
        print(f"  {regime:15s}: {count}")

    print("\nBY SYMBOL:")
    for sym, count in Counter(r["symbol"] for r in rejections).most_common():
        print(f"  {sym:10s}: {count}")

    print("\nTOP REJECTION REASONS:")
    for reason, count in Counter(r["reason_for_rejection"] for r in rejections).most_common(10):
        print(f"  {count:4d}x: {reason[:60]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    analyze(args.limit)
