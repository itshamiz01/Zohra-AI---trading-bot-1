"""
Supply and Demand Zone Detection & Lifecycle Engine for Gold (XAUUSD)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from zohra.indicators.atr import calculate_atr


class ZoneStatus:
    FRESH = "FRESH"
    TESTED = "TESTED"
    INVALIDATED = "INVALIDATED"


def detect_supply_demand_zones(df: pd.DataFrame, min_displacement_atr: float = 1.3, lookback: int = 40) -> Dict[str, List[Dict[str, Any]]]:
    """
    Identifies high-probability institutional supply and demand zones based on strong displacement.
    Returns: {"demand_zones": [...], "supply_demand": [...]}
    """
    if len(df) < lookback:
        return {"demand_zones": [], "supply_zones": []}

    atr_val = calculate_atr(df, period=14)
    if atr_val <= 0:
        atr_val = 1.0

    recent_df = df.iloc[-lookback:]
    demand_zones = []
    supply_zones = []
    current_close = float(df["close"].iloc[-1])

    for i in range(2, len(recent_df) - 1):
        bar_prev = recent_df.iloc[i - 1]
        bar_curr = recent_df.iloc[i]

        body_curr = abs(float(bar_curr["close"]) - float(bar_curr["open"]))
        range_curr = float(bar_curr["high"]) - float(bar_curr["low"])

        # ─── DEMAND ZONE (Base -> Bullish Displacement) ───
        if float(bar_curr["close"]) > float(bar_curr["open"]) and body_curr >= (min_displacement_atr * atr_val):
            zone_high = max(float(bar_prev["open"]), float(bar_prev["close"]))
            zone_low = float(bar_prev["low"])
            zone_id = f"DEMAND_{i}_{zone_low:.2f}"

            # Check status against subsequent bars
            subsequent = recent_df.iloc[i + 1:]
            touches = 0
            invalidated = False

            for _, bar in subsequent.iterrows():
                if float(bar["low"]) <= zone_low:
                    invalidated = True
                    break
                elif float(bar["low"]) <= zone_high:
                    touches += 1

            if not invalidated:
                status = ZoneStatus.TESTED if touches > 0 else ZoneStatus.FRESH
                demand_zones.append({
                    "zone_id": zone_id,
                    "type": "DEMAND",
                    "high": zone_high,
                    "low": zone_low,
                    "strength": min(100, int(70 + (body_curr / atr_val) * 15)),
                    "touches": touches,
                    "status": status,
                    "distance_to_current": current_close - zone_high
                })

        # ─── SUPPLY ZONE (Base -> Bearish Displacement) ───
        elif float(bar_curr["close"]) < float(bar_curr["open"]) and body_curr >= (min_displacement_atr * atr_val):
            zone_high = float(bar_prev["high"])
            zone_low = min(float(bar_prev["open"]), float(bar_prev["close"]))
            zone_id = f"SUPPLY_{i}_{zone_high:.2f}"

            subsequent = recent_df.iloc[i + 1:]
            touches = 0
            invalidated = False

            for _, bar in subsequent.iterrows():
                if float(bar["high"]) >= zone_high:
                    invalidated = True
                    break
                elif float(bar["high"]) >= zone_low:
                    touches += 1

            if not invalidated:
                status = ZoneStatus.TESTED if touches > 0 else ZoneStatus.FRESH
                supply_zones.append({
                    "zone_id": zone_id,
                    "type": "SUPPLY",
                    "high": zone_high,
                    "low": zone_low,
                    "strength": min(100, int(70 + (body_curr / atr_val) * 15)),
                    "touches": touches,
                    "status": status,
                    "distance_to_current": zone_low - current_close
                })

    return {
        "demand_zones": demand_zones,
        "supply_zones": supply_zones
    }


def check_supply_demand_reaction(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Checks if current price is reacting inside a fresh/tested Supply or Demand zone.
    """
    zones = detect_supply_demand_zones(df)
    last_bar = df.iloc[-1]
    close_p = float(last_bar["close"])
    high_p = float(last_bar["high"])
    low_p = float(last_bar["low"])
    open_p = float(last_bar["open"])
    candle_range = max(high_p - low_p, 1e-4)

    # 1. Demand Reaction
    for dz in zones["demand_zones"]:
        if low_p <= dz["high"] and close_p >= dz["low"]:
            lower_wick = min(open_p, close_p) - low_p
            if (lower_wick / candle_range >= 0.30) or (close_p > open_p):
                return {
                    "in_zone": True,
                    "type": "DEMAND_REACTION",
                    "direction": "BUY",
                    "zone": dz,
                    "zone_high": dz["high"],
                    "zone_low": dz["low"]
                }

    # 2. Supply Reaction
    for sz in zones["supply_zones"]:
        if high_p >= sz["low"] and close_p <= sz["high"]:
            upper_wick = high_p - max(open_p, close_p)
            if (upper_wick / candle_range >= 0.30) or (close_p < open_p):
                return {
                    "in_zone": True,
                    "type": "SUPPLY_REACTION",
                    "direction": "SELL",
                    "zone": sz,
                    "zone_high": sz["high"],
                    "zone_low": sz["low"]
                }

    return {"in_zone": False, "type": "NONE", "direction": "NONE", "zone": None}
