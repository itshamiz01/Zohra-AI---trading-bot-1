"""
Multi-Timeframe (MTF) Trend & Structure Alignment Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from zohra.indicators.ema import check_ema_alignment
from zohra.indicators.adx import calculate_adx


def calculate_mtf_alignment(df_m1: Optional[pd.DataFrame], df_m5: pd.DataFrame, df_m15: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """
    Evaluates multi-timeframe alignment across:
    - M15: Directional Trend Context (EMA 50 / 200 & ADX)
    - M5: Market Structure & Value (EMA 9 / 21)
    - M1: Timing & Trigger
    """
    if df_m5 is None or len(df_m5) < 30:
        return {"aligned": False, "direction": "NONE", "score": 0, "m15_bias": "NONE", "m5_bias": "NONE"}

    # 1. M5 Analysis
    m5_ema = check_ema_alignment(df_m5, fast=9, slow=21, trend=50)
    m5_bullish = m5_ema["bullish"]
    m5_bearish = m5_ema["bearish"]

    # 2. M15 Analysis
    m15_bullish = True
    m15_bearish = True
    m15_bias = "NEUTRAL"

    if df_m15 is not None and len(df_m15) >= 30:
        m15_ema = check_ema_alignment(df_m15, fast=9, slow=21, trend=50)
        m15_adx = calculate_adx(df_m15, period=14)
        m15_bullish = m15_ema["bullish"] or (float(df_m15["close"].iloc[-1]) > m15_ema["trend_ema"])
        m15_bearish = m15_ema["bearish"] or (float(df_m15["close"].iloc[-1]) < m15_ema["trend_ema"])
        m15_bias = "BULLISH" if m15_bullish else ("BEARISH" if m15_bearish else "NEUTRAL")

    # 3. M1 Analysis (Trigger)
    m1_bullish = True
    m1_bearish = True
    if df_m1 is not None and len(df_m1) >= 15:
        m1_ema = check_ema_alignment(df_m1, fast=9, slow=21, trend=50)
        m1_bullish = m1_ema["bullish"]
        m1_bearish = m1_ema["bearish"]

    # Overall Bullish Alignment
    if m15_bullish and m5_bullish and m1_bullish:
        return {
            "aligned": True,
            "direction": "BUY",
            "score": 95,
            "m15_bias": "BULLISH",
            "m5_bias": "BULLISH",
            "m1_trigger": "BULLISH"
        }

    # Overall Bearish Alignment
    if m15_bearish and m5_bearish and m1_bearish:
        return {
            "aligned": True,
            "direction": "SELL",
            "score": 95,
            "m15_bias": "BEARISH",
            "m5_bias": "BEARISH",
            "m1_trigger": "BEARISH"
        }

    # Partial 2-Timeframe Alignment (M15 + M5)
    if m15_bullish and m5_bullish:
        return {
            "aligned": True,
            "direction": "BUY",
            "score": 80,
            "m15_bias": "BULLISH",
            "m5_bias": "BULLISH",
            "m1_trigger": "NEUTRAL"
        }
    elif m15_bearish and m5_bearish:
        return {
            "aligned": True,
            "direction": "SELL",
            "score": 80,
            "m15_bias": "BEARISH",
            "m5_bias": "BEARISH",
            "m1_trigger": "NEUTRAL"
        }

    return {
        "aligned": False,
        "direction": "NONE",
        "score": 40,
        "m15_bias": m15_bias,
        "m5_bias": "BULLISH" if m5_bullish else ("BEARISH" if m5_bearish else "NEUTRAL"),
        "m1_trigger": "NONE"
    }
