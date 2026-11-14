"""
Market Structure, Liquidity Pools & Market Structure Shift (MSS) Engine
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any


def find_swing_points(df: pd.DataFrame, left_bars: int = 3, right_bars: int = 3) -> Tuple[List[Dict], List[Dict]]:
    """
    Finds objective swing highs and swing lows using pivot detection.
    Returns: (swing_highs, swing_lows)
    """
    swing_highs = []
    swing_lows = []
    n = len(df)

    if n < left_bars + right_bars + 1:
        return swing_highs, swing_lows

    highs = df["high"].values
    lows = df["low"].values
    times = df["timestamp"].values if "timestamp" in df.columns else df.index.values

    for i in range(left_bars, n - right_bars):
        # Check swing high
        is_high = True
        for j in range(i - left_bars, i + right_bars + 1):
            if j != i and highs[j] >= highs[i]:
                is_high = False
                break
        if is_high:
            swing_highs.append({"index": i, "price": float(highs[i]), "timestamp": times[i]})

        # Check swing low
        is_low = True
        for j in range(i - left_bars, i + right_bars + 1):
            if j != i and lows[j] <= lows[i]:
                is_low = False
                break
        if is_low:
            swing_lows.append({"index": i, "price": float(lows[i]), "timestamp": times[i]})

    return swing_highs, swing_lows


def detect_market_structure(df: pd.DataFrame, left_bars: int = 3, right_bars: int = 3) -> Dict[str, Any]:
    """
    Detects macro market structure: HIGHER_HIGH_HIGHER_LOW (BULLISH), LOWER_HIGH_LOWER_LOW (BEARISH), or RANGING.
    """
    highs, lows = find_swing_points(df, left_bars, right_bars)

    if len(highs) < 2 or len(lows) < 2:
        return {
            "structure": "RANGING",
            "last_swing_high": float(df["high"].max()) if len(df) > 0 else 0.0,
            "last_swing_low": float(df["low"].min()) if len(df) > 0 else 0.0,
            "prev_swing_high": 0.0,
            "prev_swing_low": 0.0,
            "swing_highs": highs,
            "swing_lows": lows
        }

    last_sh = highs[-1]["price"]
    prev_sh = highs[-2]["price"]
    last_sl = lows[-1]["price"]
    prev_sl = lows[-2]["price"]

    higher_highs = last_sh > prev_sh
    higher_lows = last_sl > prev_sl
    lower_highs = last_sh < prev_sh
    lower_lows = last_sl < prev_sl

    if higher_highs and higher_lows:
        structure = "BULLISH_TREND"
    elif lower_highs and lower_lows:
        structure = "BEARISH_TREND"
    elif higher_highs and lower_lows:
        structure = "EXPANDING"
    elif lower_highs and higher_lows:
        structure = "COMPRESSING"
    else:
        structure = "RANGING"

    return {
        "structure": structure,
        "last_swing_high": last_sh,
        "last_swing_low": last_sl,
        "prev_swing_high": prev_sh,
        "prev_swing_low": prev_sl,
        "swing_highs": highs,
        "swing_lows": lows
    }


def detect_liquidity_pools(df: pd.DataFrame, tolerance_pips: float = 1.0) -> Dict[str, Any]:
    """
    Finds Equal Highs (EQH - Buy-side liquidity) and Equal Lows (EQL - Sell-side liquidity).
    """
    highs, lows = find_swing_points(df, left_bars=2, right_bars=2)
    eqh = []
    eql = []
    tol = tolerance_pips * 0.10  # 1 pip in Gold = $0.10

    for i in range(len(highs) - 1):
        for j in range(i + 1, len(highs)):
            if abs(highs[i]["price"] - highs[j]["price"]) <= tol:
                eqh.append(round((highs[i]["price"] + highs[j]["price"]) / 2.0, 3))

    for i in range(len(lows) - 1):
        for j in range(i + 1, len(lows)):
            if abs(lows[i]["price"] - lows[j]["price"]) <= tol:
                eql.append(round((lows[i]["price"] + lows[j]["price"]) / 2.0, 3))

    return {
        "equal_highs": list(set(eqh)),
        "equal_lows": list(set(eql)),
        "recent_high": highs[-1]["price"] if highs else 0.0,
        "recent_low": lows[-1]["price"] if lows else 0.0
    }


def detect_liquidity_sweep(df: pd.DataFrame, lookback_bars: int = 20) -> Dict[str, Any]:
    """
    Detects if recent bars swept key swing high/low and closed back inside.
    """
    if len(df) < lookback_bars + 5:
        return {"swept": False, "type": "NONE", "level": 0.0, "sweep_extreme": 0.0}

    ref_df = df.iloc[-(lookback_bars + 5):-3]
    recent_bars = df.iloc[-3:]

    ref_high = float(ref_df["high"].max())
    ref_low = float(ref_df["low"].min())

    last_candle = df.iloc[-1]
    last_high = float(recent_bars["high"].max())
    last_low = float(recent_bars["low"].min())
    last_close = float(last_candle["close"])

    # Bearish BSL Sweep: Price wicked above ref_high but closed back BELOW ref_high
    if last_high > ref_high and last_close < ref_high:
        return {
            "swept": True,
            "type": "BSL_SWEEP",
            "direction": "BEARISH",
            "level": ref_high,
            "sweep_extreme": last_high,
            "reclaim_distance": ref_high - last_close
        }

    # Bullish SSL Sweep: Price wicked below ref_low but closed back ABOVE ref_low
    if last_low < ref_low and last_close > ref_low:
        return {
            "swept": True,
            "type": "SSL_SWEEP",
            "direction": "BULLISH",
            "level": ref_low,
            "sweep_extreme": last_low,
            "reclaim_distance": last_close - ref_low
        }

    return {"swept": False, "type": "NONE", "level": 0.0, "sweep_extreme": 0.0}


def detect_market_structure_shift(df: pd.DataFrame, sweep_info: dict) -> Dict[str, Any]:
    """
    Validates if a confirmed Market Structure Shift (MSS) occurred after a liquidity sweep.
    """
    if not sweep_info.get("swept", False):
        return {"mss_confirmed": False, "type": "NONE", "breakout_level": 0.0}

    sweep_type = sweep_info.get("type")
    last_close = float(df["close"].iloc[-1])
    highs, lows = find_swing_points(df.iloc[-30:], left_bars=2, right_bars=2)

    if sweep_type == "SSL_SWEEP":
        if highs:
            prior_lh = highs[-1]["price"]
            if last_close > prior_lh:
                return {
                    "mss_confirmed": True,
                    "type": "BULLISH_MSS",
                    "direction": "LONG",
                    "breakout_level": prior_lh,
                    "invalidation_level": sweep_info["sweep_extreme"]
                }
    elif sweep_type == "BSL_SWEEP":
        if lows:
            prior_hl = lows[-1]["price"]
            if last_close < prior_hl:
                return {
                    "mss_confirmed": True,
                    "type": "BEARISH_MSS",
                    "direction": "SHORT",
                    "breakout_level": prior_hl,
                    "invalidation_level": sweep_info["sweep_extreme"]
                }

    return {"mss_confirmed": False, "type": "NONE", "breakout_level": 0.0}
