"""
Fair Value Gap (FVG) / Imbalance Detection & Mitigation Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from zohra.indicators.atr import calculate_atr


def detect_fvgs(df: pd.DataFrame, min_gap_atr_ratio: float = 0.25, lookback: int = 30) -> Dict[str, List[Dict[str, Any]]]:
    """
    Detects 3-candle Fair Value Gaps (Bullish & Bearish imbalances).
    Bullish FVG: low[i] > high[i-2]
    Bearish FVG: high[i] < low[i-2]
    """
    if len(df) < 5:
        return {"bullish_fvgs": [], "bearish_fvgs": []}

    atr_val = calculate_atr(df, period=14)
    if atr_val <= 0:
        atr_val = 1.0

    min_gap_usd = min_gap_atr_ratio * atr_val
    bullish_fvgs = []
    bearish_fvgs = []

    start_idx = max(2, len(df) - lookback)

    for i in range(start_idx, len(df)):
        bar_prev2 = df.iloc[i - 2]
        bar_curr = df.iloc[i]

        high_2 = float(bar_prev2["high"])
        low_2 = float(bar_prev2["low"])
        high_0 = float(bar_curr["high"])
        low_0 = float(bar_curr["low"])

        # Bullish FVG
        if low_0 > high_2:
            gap_size = low_0 - high_2
            if gap_size >= min_gap_usd:
                # Check subsequent bars for mitigation
                subsequent = df.iloc[i + 1:]
                mitigated = False
                for _, sub_bar in subsequent.iterrows():
                    if float(sub_bar["low"]) <= high_2:
                        mitigated = True
                        break

                bullish_fvgs.append({
                    "index": i,
                    "top": low_0,
                    "bottom": high_2,
                    "gap_size": round(gap_size, 3),
                    "gap_atr_ratio": round(gap_size / atr_val, 2),
                    "mitigated": mitigated
                })

        # Bearish FVG
        elif high_0 < low_2:
            gap_size = low_2 - high_0
            if gap_size >= min_gap_usd:
                subsequent = df.iloc[i + 1:]
                mitigated = False
                for _, sub_bar in subsequent.iterrows():
                    if float(sub_bar["high"]) >= low_2:
                        mitigated = True
                        break

                bearish_fvgs.append({
                    "index": i,
                    "top": low_2,
                    "bottom": high_0,
                    "gap_size": round(gap_size, 3),
                    "gap_atr_ratio": round(gap_size / atr_val, 2),
                    "mitigated": mitigated
                })

    return {
        "bullish_fvgs": bullish_fvgs,
        "bearish_fvgs": bearish_fvgs
    }


def check_fvg_retest(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Checks if current candle is actively filling / retesting an unmitigated FVG and printing a reaction.
    """
    fvgs = detect_fvgs(df)
    last_bar = df.iloc[-1]
    close_p = float(last_bar["close"])
    high_p = float(last_bar["high"])
    low_p = float(last_bar["low"])
    open_p = float(last_bar["open"])
    candle_range = max(high_p - low_p, 1e-4)

    # 1. Bullish FVG Retest (price dips into bullish gap and reacts upward)
    for fvg in reversed(fvgs["bullish_fvgs"]):
        if not fvg["mitigated"]:
            if low_p <= fvg["top"] and close_p >= fvg["bottom"]:
                lower_wick = min(open_p, close_p) - low_p
                if (lower_wick / candle_range >= 0.25) or (close_p > open_p):
                    return {
                        "retest": True,
                        "direction": "BUY",
                        "type": "BULLISH_FVG_RETEST",
                        "fvg": fvg,
                        "fvg_top": fvg["top"],
                        "fvg_bottom": fvg["bottom"]
                    }

    # 2. Bearish FVG Retest (price pushes up into bearish gap and reacts downward)
    for fvg in reversed(fvgs["bearish_fvgs"]):
        if not fvg["mitigated"]:
            if high_p >= fvg["bottom"] and close_p <= fvg["top"]:
                upper_wick = high_p - max(open_p, close_p)
                if (upper_wick / candle_range >= 0.25) or (close_p < open_p):
                    return {
                        "retest": True,
                        "direction": "SELL",
                        "type": "BEARISH_FVG_RETEST",
                        "fvg": fvg,
                        "fvg_top": fvg["top"],
                        "fvg_bottom": fvg["bottom"]
                    }

    return {"retest": False, "direction": "NONE", "type": "NONE", "fvg": None}
