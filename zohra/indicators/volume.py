"""
Tick Volume & Relative Volume (RVOL) Expansion Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any


def calculate_relative_volume(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    """
    Calculates Relative Volume (RVOL) based on MT5 tick volume.
    RVOL = current_tick_volume / SMA(tick_volume, period)
    """
    if len(df) < period + 1:
        return {"rvol": 1.0, "is_high_volume": False, "is_climax": False, "avg_volume": 0.0}

    vol_col = "tick_volume" if "tick_volume" in df.columns else ("volume" if "volume" in df.columns else None)
    if vol_col is None:
        return {"rvol": 1.0, "is_high_volume": False, "is_climax": False, "avg_volume": 0.0}

    volumes = df[vol_col].astype(float)
    avg_vol = volumes.iloc[-period - 1:-1].mean()
    current_vol = volumes.iloc[-1]

    rvol = current_vol / avg_vol if avg_vol > 0 else 1.0
    rvol = round(float(rvol), 2)

    return {
        "rvol": rvol,
        "current_volume": float(current_vol),
        "avg_volume": float(avg_vol),
        "is_high_volume": rvol >= 1.4,
        "is_climax": rvol >= 2.5
    }


def check_volume_breakout(df: pd.DataFrame, min_rvol: float = 1.35) -> Dict[str, Any]:
    """
    Checks if current candle is breaking a consolidation range accompanied by significant Relative Volume expansion.
    """
    vol_data = calculate_relative_volume(df, period=20)
    if not vol_data["is_high_volume"] and vol_data["rvol"] < min_rvol:
        return {"volume_confirmed": False, "rvol": vol_data["rvol"], "direction": "NONE"}

    last_bar = df.iloc[-1]
    prev_bars = df.iloc[-21:-1]
    high_20 = float(prev_bars["high"].max())
    low_20 = float(prev_bars["low"].min())
    close_p = float(last_bar["close"])

    if close_p > high_20:
        return {
            "volume_confirmed": True,
            "direction": "BUY",
            "rvol": vol_data["rvol"],
            "breakout_level": high_20
        }
    elif close_p < low_20:
        return {
            "volume_confirmed": True,
            "direction": "SELL",
            "rvol": vol_data["rvol"],
            "breakout_level": low_20
        }

    return {"volume_confirmed": False, "rvol": vol_data["rvol"], "direction": "NONE"}
