"""
Volume Weighted Average Price (VWAP) Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculates cumulative session Volume Weighted Average Price (VWAP) Series.
    """
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)

    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol_col = "tick_volume" if "tick_volume" in df.columns else ("volume" if "volume" in df.columns else None)

    if vol_col and vol_col in df.columns:
        vol = df[vol_col].astype(float).replace(0, 1.0)
        pv = tp * vol
        vwap = pv.cumsum() / (vol.cumsum() + 1e-9)
    else:
        vwap = tp.expanding().mean()

    return vwap


def calculate_session_vwap(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculates session VWAP, slope, and cross-count rotational metrics.
    """
    if df is None or len(df) == 0:
        return {"vwap": pd.Series(dtype=float), "current_vwap": 0.0, "vwap_slope": 0.0, "cross_count": 0}

    vwap = calculate_vwap(df)
    current_vwap = float(vwap.iloc[-1])

    slope = 0.0
    if len(vwap) >= 6:
        slope = float(vwap.iloc[-1] - vwap.iloc[-6]) / 5.0

    cross_count = 0
    if len(df) >= 20:
        diff = df["close"].iloc[-20:] - vwap.iloc[-20:]
        cross_count = int(((diff * diff.shift(1)) < 0).sum())

    return {
        "vwap": vwap,
        "current_vwap": current_vwap,
        "vwap_slope": slope,
        "cross_count": cross_count
    }


def calculate_vwap_distance_atr(current_price: float, vwap_price: float, atr_value: float) -> float:
    """Calculates distance between current price and VWAP normalized by ATR."""
    if atr_value <= 0:
        return 0.0
    return float((current_price - vwap_price) / atr_value)
