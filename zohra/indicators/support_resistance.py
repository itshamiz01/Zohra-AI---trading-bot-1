"""
Support & Resistance Level Detection & Quality Scoring Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from zohra.indicators.market_structure import find_swing_points
from zohra.indicators.atr import calculate_atr


def detect_key_levels(df: pd.DataFrame, tolerance_usd: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Detects dynamic & static support/resistance levels, pivot clusters, and session highs/lows.
    Returns sorted list of levels with quality score (0-100).
    Dynamically scales tolerance for both Gold and Forex pairs.
    """
    if len(df) < 20:
        return []

    atr_val = calculate_atr(df, period=14)
    last_close = float(df["close"].iloc[-1]) if "close" in df.columns and len(df) > 0 else 1.0

    if tolerance_usd is None or (tolerance_usd >= 1.0 and last_close < 500):
        # Dynamically scale for Forex / non-gold
        tolerance = max(0.3 * atr_val, 0.0001 if last_close < 10 else 0.01)
    else:
        tolerance = tolerance_usd

    highs, lows = find_swing_points(df, left_bars=2, right_bars=2)
    raw_points = [h["price"] for h in highs] + [l["price"] for l in lows]

    # Add Previous Day / Session High & Low if available
    pdh = float(df["high"].max())
    pdl = float(df["low"].min())
    raw_points.extend([pdh, pdl])

    # Cluster close points together
    clusters: List[List[float]] = []
    for pt in raw_points:
        matched = False
        for c in clusters:
            avg_c = sum(c) / len(c)
            if abs(pt - avg_c) <= tolerance:
                c.append(pt)
                matched = True
                break
        if not matched:
            clusters.append([pt])

    scored_levels = []
    for c in clusters:
        price_lvl = round(sum(c) / len(c), 5 if last_close < 10 else 3)
        touch_count = len(c)

        # Quality scoring
        # 1. Touches (up to 40 pts)
        score_touches = min(40, touch_count * 15)

        # 2. Recency (up to 30 pts)
        recent_touches = sum(1 for pt in c if abs(pt - price_lvl) <= tolerance)
        score_recency = min(30, recent_touches * 10)

        # 3. Round Number Confluence
        if last_close > 500:
            is_round = (round(price_lvl) % 10 == 0) or (round(price_lvl) % 5 == 0)
        elif last_close > 20:
            is_round = (round(price_lvl, 1) % 0.5 == 0)
        else:
            # Forex psychological levels (00, 50 pips)
            is_round = (round(price_lvl * 100, 1) % 0.5 == 0)
        score_round = 25 if is_round else 10

        total_score = min(100, score_touches + score_recency + score_round)

        scored_levels.append({
            "price": price_lvl,
            "touches": touch_count,
            "score": total_score,
            "is_round_number": is_round
        })

    # Sort descending by score
    scored_levels.sort(key=lambda x: x["score"], reverse=True)
    return scored_levels


def check_sr_rejection(df: pd.DataFrame, tolerance_usd: Optional[float] = None) -> Dict[str, Any]:
    """
    Checks if current candle is testing a high-quality S/R level and printing a confirmed rejection.
    """
    atr_val = calculate_atr(df, period=14)
    last_close = float(df["close"].iloc[-1]) if "close" in df.columns and len(df) > 0 else 1.0

    if tolerance_usd is None or (tolerance_usd >= 1.0 and last_close < 500):
        tolerance = max(0.25 * atr_val, 0.0001 if last_close < 10 else 0.01)
    else:
        tolerance = tolerance_usd

    levels = detect_key_levels(df, tolerance)
    if not levels or len(df) < 5:
        return {"rejection": False, "type": "NONE", "level": 0.0, "score": 0}

    last_bar = df.iloc[-1]
    close_p = float(last_bar["close"])
    high_p = float(last_bar["high"])
    low_p = float(last_bar["low"])
    open_p = float(last_bar["open"])
    candle_range = max(high_p - low_p, 1e-6 if last_close < 10 else 1e-4)

    for lvl_dict in levels[:5]:  # Check top 5 levels
        lvl = lvl_dict["price"]
        score = lvl_dict["score"]

        # 1. Bullish Support Rejection
        # Low pierced or touched near support, closed above support with lower wick
        if abs(low_p - lvl) <= tolerance or (low_p <= lvl and close_p > lvl):
            lower_wick = min(open_p, close_p) - low_p
            if (lower_wick / candle_range >= 0.35) or (close_p > open_p and close_p > lvl):
                return {
                    "rejection": True,
                    "type": "SUPPORT_REJECTION",
                    "direction": "BUY",
                    "level": lvl,
                    "score": score,
                    "lower_wick_ratio": round(lower_wick / candle_range, 2)
                }

        # 2. Bearish Resistance Rejection
        # High pierced or touched near resistance, closed below resistance with upper wick
        if abs(high_p - lvl) <= tolerance or (high_p >= lvl and close_p < lvl):
            upper_wick = high_p - max(open_p, close_p)
            if (upper_wick / candle_range >= 0.35) or (close_p < open_p and close_p < lvl):
                return {
                    "rejection": True,
                    "type": "RESISTANCE_REJECTION",
                    "direction": "SELL",
                    "level": lvl,
                    "score": score,
                    "upper_wick_ratio": upper_wick / candle_range
                }

    return {"rejection": False, "type": "NONE", "level": 0.0, "score": 0}
