"""
Order Block (OB) Detection & Retest Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from zohra.indicators.atr import calculate_atr
from zohra.indicators.market_structure import find_swing_points


def detect_order_blocks(df: pd.DataFrame, min_displacement_atr: float = 1.2, lookback: int = 35) -> Dict[str, List[Dict[str, Any]]]:
    """
    Detects institutional order blocks:
    Bullish OB: The last down candle (bearish) before a powerful upward displacement that breaks local structure.
    Bearish OB: The last up candle (bullish) before a powerful downward displacement that breaks local structure.
    """
    if len(df) < lookback:
        return {"bullish_obs": [], "bearish_obs": []}

    atr_val = calculate_atr(df, period=14)
    if atr_val <= 0:
        atr_val = 1.0

    recent_df = df.iloc[-lookback:]
    bullish_obs = []
    bearish_obs = []

    for i in range(1, len(recent_df) - 2):
        ob_bar = recent_df.iloc[i]
        next_bars = recent_df.iloc[i + 1: min(i + 4, len(recent_df))]

        # Check Bullish OB: Bearish candle (close < open) followed by strong multi-bar bullish impulse
        if float(ob_bar["close"]) < float(ob_bar["open"]):
            impulse_high = float(next_bars["high"].max())
            displacement = impulse_high - float(ob_bar["high"])
            if displacement >= (min_displacement_atr * atr_val):
                ob_high = float(ob_bar["high"])
                ob_low = float(ob_bar["low"])

                # Check if mitigated
                subsequent = recent_df.iloc[i + 3:]
                mitigated = False
                for _, bar in subsequent.iterrows():
                    if float(bar["low"]) <= ob_low:
                        mitigated = True
                        break

                if not mitigated:
                    bullish_obs.append({
                        "type": "BULLISH_OB",
                        "high": ob_high,
                        "low": ob_low,
                        "displacement": displacement,
                        "mitigated": mitigated
                    })

        # Check Bearish OB: Bullish candle (close > open) followed by strong multi-bar bearish impulse
        elif float(ob_bar["close"]) > float(ob_bar["open"]):
            impulse_low = float(next_bars["low"].min())
            displacement = float(ob_bar["low"]) - impulse_low
            if displacement >= (min_displacement_atr * atr_val):
                ob_high = float(ob_bar["high"])
                ob_low = float(ob_bar["low"])

                # Check if mitigated
                subsequent = recent_df.iloc[i + 3:]
                mitigated = False
                for _, bar in subsequent.iterrows():
                    if float(bar["high"]) >= ob_high:
                        mitigated = True
                        break

                if not mitigated:
                    bearish_obs.append({
                        "type": "BEARISH_OB",
                        "high": ob_high,
                        "low": ob_low,
                        "displacement": displacement,
                        "mitigated": mitigated
                    })

    return {
        "bullish_obs": bullish_obs,
        "bearish_obs": bearish_obs
    }


def check_order_block_retest(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Checks if current candle is retesting an active Order Block and printing rejection.
    """
    obs = detect_order_blocks(df)
    last_bar = df.iloc[-1]
    close_p = float(last_bar["close"])
    high_p = float(last_bar["high"])
    low_p = float(last_bar["low"])
    open_p = float(last_bar["open"])
    candle_range = max(high_p - low_p, 1e-4)

    # 1. Bullish OB Retest
    for ob in reversed(obs["bullish_obs"]):
        if not ob["mitigated"]:
            if low_p <= ob["high"] and close_p >= ob["low"]:
                lower_wick = min(open_p, close_p) - low_p
                if (lower_wick / candle_range >= 0.25) or (close_p > open_p):
                    return {
                        "retest": True,
                        "direction": "BUY",
                        "type": "BULLISH_OB_RETEST",
                        "ob": ob,
                        "ob_high": ob["high"],
                        "ob_low": ob["low"]
                    }

    # 2. Bearish OB Retest
    for ob in reversed(obs["bearish_obs"]):
        if not ob["mitigated"]:
            if high_p >= ob["low"] and close_p <= ob["high"]:
                upper_wick = high_p - max(open_p, close_p)
                if (upper_wick / candle_range >= 0.25) or (close_p < open_p):
                    return {
                        "retest": True,
                        "direction": "SELL",
                        "type": "BEARISH_OB_RETEST",
                        "ob": ob,
                        "ob_high": ob["high"],
                        "ob_low": ob["low"]
                    }

    return {"retest": False, "direction": "NONE", "type": "NONE", "ob": None}
