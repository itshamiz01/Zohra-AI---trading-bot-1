"""
Bollinger Bands & Statistical Volatility Compression/Extreme Engine
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, num_std: float = 2.0, column: str = "close") -> Dict[str, Any]:
    """Calculates Bollinger Bands (Upper, Middle, Lower, Bandwidth, %B)."""
    if df is None or len(df) < period:
        return {
            "upper": pd.Series(dtype=float), "middle": pd.Series(dtype=float), "lower": pd.Series(dtype=float),
            "bandwidth": pd.Series(dtype=float), "percent_b": pd.Series(dtype=float),
            "latest_upper": 0.0, "latest_middle": 0.0, "latest_lower": 0.0,
            "latest_bandwidth": 0.0, "latest_percent_b": 0.5
        }

    middle = df[column].rolling(period).mean()
    std = df[column].rolling(period).std()

    upper = middle + (std * num_std)
    lower = middle - (std * num_std)

    bandwidth = ((upper - lower) / (middle + 1e-9)) * 100.0
    percent_b = (df[column] - lower) / ((upper - lower) + 1e-9)

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
        "latest_upper": float(upper.iloc[-1]),
        "latest_middle": float(middle.iloc[-1]),
        "latest_lower": float(lower.iloc[-1]),
        "latest_bandwidth": float(bandwidth.iloc[-1]),
        "latest_percent_b": float(percent_b.iloc[-1])
    }


def check_bollinger_extreme(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> Dict[str, Any]:
    """
    Checks if recent price has pierced the outer Bollinger Bands and is reverting.
    """
    bb = calculate_bollinger_bands(df, period, num_std)
    if len(df) < 3:
        return {"extreme": False, "type": "NONE", "bandwidth": 0.0}

    last_bar = df.iloc[-1]
    close_p = float(last_bar["close"])
    recent_high = float(df["high"].iloc[-3:].max())
    recent_low = float(df["low"].iloc[-3:].min())

    upper = bb["latest_upper"]
    lower = bb["latest_lower"]
    middle = bb["latest_middle"]

    if recent_high >= upper and close_p < upper:
        return {
            "extreme": True,
            "type": "OVERBOUGHT_REVERSION",
            "direction": "SELL",
            "band_level": upper,
            "middle": middle,
            "bandwidth": bb["latest_bandwidth"]
        }
    elif recent_low <= lower and close_p > lower:
        return {
            "extreme": True,
            "type": "OVERSOLD_REVERSION",
            "direction": "BUY",
            "band_level": lower,
            "middle": middle,
            "bandwidth": bb["latest_bandwidth"]
        }

    return {"extreme": False, "type": "NONE", "direction": "NONE", "bandwidth": bb["latest_bandwidth"]}
