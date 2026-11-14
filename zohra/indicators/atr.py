"""
Average True Range (ATR) & Volatility Compression/Expansion Engine
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Union


def calculate_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculates True Range and rolling Average True Range Series."""
    if df is None or len(df) < 2:
        return pd.Series(dtype=float)

    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return tr.rolling(window=period, min_periods=1).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Returns scalar current ATR float value scaled appropriately for the instrument.
    Prevents hardcoded Gold thresholds from inflating Forex ATRs by 1000x.
    """
    if df is None or len(df) < 2:
        return 1.0
    
    last_close = float(df["close"].iloc[-1]) if "close" in df.columns and len(df) > 0 else 1.0
    if last_close > 500:
        min_floor = 0.10       # Gold, Silver, BTC, Indices
    elif last_close > 20:
        min_floor = 0.01       # JPY pairs, oil
    else:
        min_floor = 0.00005    # Standard Forex (EURUSD, GBPUSD)

    series = calculate_atr_series(df, period)
    val = float(series.iloc[-1]) if len(series) > 0 and not np.isnan(series.iloc[-1]) else min_floor
    return max(val, min_floor)


def calculate_relative_atr_expansion(df: pd.DataFrame, atr_period: int = 14, sma_period: int = 20) -> Dict[str, Any]:
    """
    Measures current ATR relative to baseline 20-period SMA of ATR.
    """
    atr_s = calculate_atr_series(df, atr_period)
    if len(atr_s) < sma_period + 2:
        return {"current_atr": 1.0, "baseline_atr": 1.0, "expansion_ratio": 1.0, "state": "NORMAL"}

    curr_atr = float(atr_s.iloc[-1])
    base_atr = float(atr_s.iloc[-sma_period - 1:-1].mean())
    if base_atr <= 0:
        base_atr = 1.0

    ratio = round(curr_atr / base_atr, 2)
    if ratio >= 1.4:
        state = "HIGH_EXPANSION"
    elif ratio >= 1.15:
        state = "MODERATE_EXPANSION"
    elif ratio <= 0.75:
        state = "COMPRESSION"
    else:
        state = "NORMAL"

    return {
        "current_atr": round(curr_atr, 3),
        "baseline_atr": round(base_atr, 3),
        "expansion_ratio": ratio,
        "state": state
    }


def detect_atr_compression_expansion(df: pd.DataFrame, compression_bars: int = 5) -> Dict[str, Any]:
    """
    Detects volatility cycle transition:
    Recent compression (ATR was below 0.8x SMA for multiple bars) followed by current expansion (ATR > 1.15x SMA).
    """
    atr_s = calculate_atr_series(df, period=14)
    if len(atr_s) < 25:
        return {"compression_breakout": False, "compression_ratio": 1.0, "current_ratio": 1.0}

    sma_20 = atr_s.rolling(20).mean()
    ratios = (atr_s / sma_20).dropna()

    if len(ratios) < compression_bars + 1:
        return {"compression_breakout": False, "compression_ratio": 1.0, "current_ratio": 1.0}

    recent_ratios = ratios.iloc[-compression_bars - 1:-1]
    curr_ratio = float(ratios.iloc[-1])

    was_compressed = (recent_ratios.mean() <= 0.82)
    now_expanding = (curr_ratio >= 1.15)

    return {
        "compression_breakout": was_compressed and now_expanding,
        "was_compressed": was_compressed,
        "now_expanding": now_expanding,
        "compression_ratio": round(float(recent_ratios.mean()), 2),
        "current_ratio": round(curr_ratio, 2)
    }
