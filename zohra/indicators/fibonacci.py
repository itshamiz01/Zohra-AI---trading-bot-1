"""
Fibonacci Retracement & Extension Indicator for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from zohra.indicators.market_structure import find_swing_points


def calculate_fibonacci_levels(high_price: float, low_price: float, is_uptrend: bool) -> Dict[str, float]:
    """
    Calculates Fibonacci retracement levels for a given price impulse.
    """
    diff = high_price - low_price
    if diff <= 0:
        return {}

    if is_uptrend:
        # Retracement down from high
        return {
            "0.0": round(high_price, 3),
            "0.236": round(high_price - (0.236 * diff), 3),
            "0.382": round(high_price - (0.382 * diff), 3),
            "0.500": round(high_price - (0.500 * diff), 3),
            "0.618": round(high_price - (0.618 * diff), 3),  # Golden pocket lower
            "0.786": round(high_price - (0.786 * diff), 3),  # Deep retracement
            "1.0": round(low_price, 3)
        }
    else:
        # Retracement up from low
        return {
            "0.0": round(low_price, 3),
            "0.236": round(low_price + (0.236 * diff), 3),
            "0.382": round(low_price + (0.382 * diff), 3),
            "0.500": round(low_price + (0.500 * diff), 3),
            "0.618": round(low_price + (0.618 * diff), 3),  # Golden pocket upper
            "0.786": round(low_price + (0.786 * diff), 3),  # Deep retracement
            "1.0": round(high_price, 3)
        }


def detect_fibonacci_retracement(df: pd.DataFrame, is_uptrend: bool, lookback: int = 30) -> Dict[str, Any]:
    """
    Detects if current price is testing the Golden Pocket (38.2% - 61.8%) of the most recent significant impulse.
    """
    if len(df) < lookback:
        return {"in_zone": False, "level": 0.0, "zone": "NONE", "levels": {}}

    highs, lows = find_swing_points(df.iloc[-lookback:], left_bars=2, right_bars=2)
    if not highs or not lows:
        return {"in_zone": False, "level": 0.0, "zone": "NONE", "levels": {}}

    last_high = highs[-1]["price"]
    last_low = lows[-1]["price"]
    last_close = float(df["close"].iloc[-1])

    if last_high <= last_low:
        return {"in_zone": False, "level": 0.0, "zone": "NONE", "levels": {}}

    levels = calculate_fibonacci_levels(last_high, last_low, is_uptrend)
    if not levels:
        return {"in_zone": False, "level": 0.0, "zone": "NONE", "levels": {}}

    if is_uptrend:
        fib_382 = levels["0.382"]
        fib_500 = levels["0.500"]
        fib_618 = levels["0.618"]
        fib_786 = levels["0.786"]

        # Golden pocket zone: between 38.2% and 61.8% (or deep 78.6%)
        in_golden_pocket = (last_close <= fib_382 + 0.5) and (last_close >= fib_618 - 0.5)
        in_deep_pocket = (last_close < fib_618) and (last_close >= fib_786 - 0.5)

        if in_golden_pocket:
            return {
                "in_zone": True,
                "zone": "GOLDEN_POCKET",
                "nearest_level": fib_500 if abs(last_close - fib_500) < abs(last_close - fib_618) else fib_618,
                "impulse_high": last_high,
                "impulse_low": last_low,
                "levels": levels
            }
        elif in_deep_pocket:
            return {
                "in_zone": True,
                "zone": "DEEP_POCKET",
                "nearest_level": fib_786,
                "impulse_high": last_high,
                "impulse_low": last_low,
                "levels": levels
            }
    else:
        fib_382 = levels["0.382"]
        fib_500 = levels["0.500"]
        fib_618 = levels["0.618"]
        fib_786 = levels["0.786"]

        # Golden pocket zone: between 38.2% and 61.8% (or deep 78.6%)
        in_golden_pocket = (last_close >= fib_382 - 0.5) and (last_close <= fib_618 + 0.5)
        in_deep_pocket = (last_close > fib_618) and (last_close <= fib_786 + 0.5)

        if in_golden_pocket:
            return {
                "in_zone": True,
                "zone": "GOLDEN_POCKET",
                "nearest_level": fib_500 if abs(last_close - fib_500) < abs(last_close - fib_618) else fib_618,
                "impulse_high": last_high,
                "impulse_low": last_low,
                "levels": levels
            }
        elif in_deep_pocket:
            return {
                "in_zone": True,
                "zone": "DEEP_POCKET",
                "nearest_level": fib_786,
                "impulse_high": last_high,
                "impulse_low": last_low,
                "levels": levels
            }

    return {"in_zone": False, "level": 0.0, "zone": "NONE", "levels": levels}
