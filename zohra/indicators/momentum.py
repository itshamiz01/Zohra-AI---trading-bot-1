"""
Momentum Candle Displacement & Continuation Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from zohra.indicators.atr import calculate_atr


def detect_momentum_candle(df: pd.DataFrame, min_body_ratio: float = 0.65, min_atr_multiple: float = 1.3) -> Dict[str, Any]:
    """
    Detects an unusually strong institutional momentum candle:
    - Body >= 65% of candle range
    - Range >= 1.3x ATR
    - Close near the candle high (bullish) or candle low (bearish)
    """
    if len(df) < 5:
        return {"has_momentum": False, "direction": "NONE", "body_ratio": 0.0, "atr_multiple": 0.0}

    atr_val = calculate_atr(df, period=14)
    if atr_val <= 0:
        atr_val = 1.0

    last_bar = df.iloc[-1]
    prev_bar = df.iloc[-2]

    close_p = float(last_bar["close"])
    open_p = float(last_bar["open"])
    high_p = float(last_bar["high"])
    low_p = float(last_bar["low"])

    candle_range = max(high_p - low_p, 1e-4)
    body_size = abs(close_p - open_p)
    body_ratio = body_size / candle_range
    atr_multiple = candle_range / atr_val

    is_significant = (body_ratio >= min_body_ratio) and (atr_multiple >= min_atr_multiple)

    # Bullish momentum
    if is_significant and close_p > open_p and (high_p - close_p) / candle_range <= 0.20:
        return {
            "has_momentum": True,
            "direction": "BUY",
            "body_ratio": round(body_ratio, 2),
            "atr_multiple": round(atr_multiple, 2),
            "candle_high": high_p,
            "candle_low": low_p
        }

    # Bearish momentum
    elif is_significant and close_p < open_p and (close_p - low_p) / candle_range <= 0.20:
        return {
            "has_momentum": True,
            "direction": "SELL",
            "body_ratio": round(body_ratio, 2),
            "atr_multiple": round(atr_multiple, 2),
            "candle_high": high_p,
            "candle_low": low_p
        }

    # Check continuation setup: Previous bar was momentum candle, current bar is controlled shallow pullback
    prev_close = float(prev_bar["close"])
    prev_open = float(prev_bar["open"])
    prev_high = float(prev_bar["high"])
    prev_low = float(prev_bar["low"])
    prev_range = max(prev_high - prev_low, 1e-4)
    prev_body = abs(prev_close - prev_open)
    prev_is_mom = (prev_body / prev_range >= min_body_ratio) and (prev_range / atr_val >= min_atr_multiple)

    if prev_is_mom:
        # Bullish shallow pullback continuation: holds upper half of previous body and shows bullish reaction
        if prev_close > prev_open:
            midpoint = prev_open + (0.5 * prev_body)
            has_reaction = (close_p >= open_p) or ((min(open_p, close_p) - low_p) / candle_range >= 0.30)
            if low_p >= midpoint and close_p > prev_open and has_reaction:
                return {
                    "has_momentum": True,
                    "direction": "BUY",
                    "is_continuation_pullback": True,
                    "body_ratio": round(prev_body / prev_range, 2),
                    "atr_multiple": round(prev_range / atr_val, 2),
                    "candle_high": prev_high,
                    "candle_low": prev_low
                }

        # Bearish shallow pullback continuation: holds lower half of previous body and shows bearish reaction
        elif prev_close < prev_open:
            midpoint = prev_open - (0.5 * prev_body)
            has_reaction = (close_p <= open_p) or ((high_p - max(open_p, close_p)) / candle_range >= 0.30)
            if high_p <= midpoint and close_p < prev_open and has_reaction:
                return {
                    "has_momentum": True,
                    "direction": "SELL",
                    "is_continuation_pullback": True,
                    "body_ratio": round(prev_body / prev_range, 2),
                    "atr_multiple": round(prev_range / atr_val, 2),
                    "candle_high": prev_high,
                    "candle_low": prev_low
                }

    return {"has_momentum": False, "direction": "NONE", "body_ratio": round(body_ratio, 2), "atr_multiple": round(atr_multiple, 2)}
