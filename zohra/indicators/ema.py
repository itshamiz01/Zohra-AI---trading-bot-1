"""
Exponential Moving Average (EMA) & Trend Alignment Engine
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Any, Optional


def calculate_ema(df: pd.DataFrame, span: int, column: str = "close") -> pd.Series:
    """Calculates Exponential Moving Average (EMA)."""
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)
    return df[column].ewm(span=span, adjust=False).mean()


def calculate_ema_slope(ema_series: pd.Series, lookback: int = 3) -> float:
    """Calculates slope of EMA over recent candles in price points per bar."""
    if len(ema_series) < lookback + 1:
        return 0.0
    return float((ema_series.iloc[-1] - ema_series.iloc[-1 - lookback]) / lookback)


def check_ema_alignment(df: pd.DataFrame, fast: int = 9, slow: int = 21, trend: int = 50) -> Dict[str, Any]:
    """
    Evaluates fast/slow/trend EMA alignment and slopes.
    """
    if df is None or len(df) < 5:
        return {
            "alignment": "FLAT", "bullish": False, "bearish": False,
            "fast_ema": 0.0, "slow_ema": 0.0, "trend_ema": 0.0,
            "fast_slope": 0.0, "slow_slope": 0.0, "slope_strength": "FLAT"
        }

    ema_f = calculate_ema(df, fast)
    ema_s = calculate_ema(df, slow)
    ema_t = calculate_ema(df, trend)

    f_val = float(ema_f.iloc[-1])
    s_val = float(ema_s.iloc[-1])
    t_val = float(ema_t.iloc[-1]) if len(ema_t) > 0 and not np.isnan(ema_t.iloc[-1]) else s_val

    slope_f = calculate_ema_slope(ema_f, lookback=3)
    slope_s = calculate_ema_slope(ema_s, lookback=3)

    is_bull = (f_val > s_val) and (s_val >= t_val) and (slope_f > 0)
    is_bear = (f_val < s_val) and (s_val <= t_val) and (slope_f < 0)

    if is_bull:
        alignment = "BULLISH"
    elif is_bear:
        alignment = "BEARISH"
    else:
        alignment = "FLAT"

    if abs(slope_f) >= 0.4:
        slope_strength = "STRONG"
    elif abs(slope_f) >= 0.15:
        slope_strength = "MODERATE"
    else:
        slope_strength = "FLAT"

    return {
        "alignment": alignment,
        "bullish": is_bull,
        "bearish": is_bear,
        "fast_ema": round(f_val, 3),
        "slow_ema": round(s_val, 3),
        "trend_ema": round(t_val, 3),
        "fast_slope": round(slope_f, 3),
        "slow_slope": round(slope_s, 3),
        "slope_strength": slope_strength,
        "fast": ema_f,
        "slow": ema_s,
        "trend": ema_t
    }


def calculate_ema_ribbon(df: pd.DataFrame, fast: int = 8, slow: int = 21, trend: int = 50) -> Dict[str, Any]:
    """Calculates fast, slow, and trend EMAs and alignment status (legacy compatibility)."""
    res = check_ema_alignment(df, fast, slow, trend)
    return {
        "fast": res["fast"],
        "slow": res["slow"],
        "trend": res["trend"],
        "latest_fast": res["fast_ema"],
        "latest_slow": res["slow_ema"],
        "latest_trend": res["trend_ema"],
        "slope_fast": res["fast_slope"],
        "slope_slow": res["slow_slope"],
        "is_bullish": res["bullish"],
        "is_bearish": res["bearish"],
        "zone_top": max(res["fast_ema"], res["slow_ema"]),
        "zone_bottom": min(res["fast_ema"], res["slow_ema"])
    }
