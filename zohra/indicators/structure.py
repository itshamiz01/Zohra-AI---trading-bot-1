import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any

def detect_swings(df: pd.DataFrame, lookback: int = 5) -> Tuple[List[Dict], List[Dict]]:
    """
    Detects fractal swing highs and swing lows over a rolling window.
    Returns (swing_highs, swing_lows).
    """
    swing_highs = []
    swing_lows = []
    
    if len(df) < lookback * 2 + 1:
        return swing_highs, swing_lows
    
    highs = df['high'].values
    lows = df['low'].values
    times = df.index
    
    for i in range(lookback, len(df) - lookback):
        # Swing High: Highest point in [i - lookback, i + lookback]
        if highs[i] == max(highs[i - lookback : i + lookback + 1]):
            swing_highs.append({
                "index": i,
                "price": float(highs[i]),
                "time": str(times[i])
            })
        # Swing Low: Lowest point in [i - lookback, i + lookback]
        if lows[i] == min(lows[i - lookback : i + lookback + 1]):
            swing_lows.append({
                "index": i,
                "price": float(lows[i]),
                "time": str(times[i])
            })
            
    return swing_highs, swing_lows

def detect_equal_levels(swing_highs: List[Dict], swing_lows: List[Dict], threshold_pips: float = 3.0, point: float = 0.01) -> Dict[str, Any]:
    """Detects Equal Highs (EQH - Buy-side Liquidity) and Equal Lows (EQL - Sell-side Liquidity)."""
    eqh = []
    eql = []
    
    thresh = threshold_pips * (point * 10.0)  # Gold 1 pip = 0.10
    
    # Check swing highs
    if len(swing_highs) >= 2:
        for i in range(len(swing_highs) - 1):
            for j in range(i + 1, len(swing_highs)):
                if abs(swing_highs[i]["price"] - swing_highs[j]["price"]) <= thresh:
                    eqh.append({
                        "level": (swing_highs[i]["price"] + swing_highs[j]["price"]) / 2.0,
                        "high1": swing_highs[i],
                        "high2": swing_highs[j]
                    })
                    
    # Check swing lows
    if len(swing_lows) >= 2:
        for i in range(len(swing_lows) - 1):
            for j in range(i + 1, len(swing_lows)):
                if abs(swing_lows[i]["price"] - swing_lows[j]["price"]) <= thresh:
                    eql.append({
                        "level": (swing_lows[i]["price"] + swing_lows[j]["price"]) / 2.0,
                        "low1": swing_lows[i],
                        "low2": swing_lows[j]
                    })
                    
    return {"eqh": eqh, "eql": eql}

def detect_liquidity_sweep(df: pd.DataFrame, swing_highs: List[Dict], swing_lows: List[Dict]) -> Dict[str, Any]:
    """
    Checks if the latest candle swept liquidity above a recent swing high (BSL) or below a swing low (SSL),
    and then closed back inside the range.
    """
    if len(df) < 5 or (not swing_highs and not swing_lows):
        return {"swept": False, "type": None, "level": 0.0, "extreme": 0.0}
    
    latest = df.iloc[-1]
    
    # 1. Check Bullish Sweep (Sell-side liquidity swept below recent swing low, candle closes above)
    if swing_lows:
        recent_low = swing_lows[-1]
        low_level = recent_low["price"]
        if latest['low'] < low_level and latest['close'] > low_level:
            return {
                "swept": True,
                "type": "SSL",
                "level": low_level,
                "extreme": float(latest['low']),
                "candle_index": len(df) - 1
            }
            
    # 2. Check Bearish Sweep (Buy-side liquidity swept above recent swing high, candle closes below)
    if swing_highs:
        recent_high = swing_highs[-1]
        high_level = recent_high["price"]
        if latest['high'] > high_level and latest['close'] < high_level:
            return {
                "swept": True,
                "type": "BSL",
                "level": high_level,
                "extreme": float(latest['high']),
                "candle_index": len(df) - 1
            }
            
    return {"swept": False, "type": None, "level": 0.0, "extreme": 0.0}

def detect_mss(df: pd.DataFrame, sweep_info: Dict[str, Any], swing_highs: List[Dict], swing_lows: List[Dict]) -> Dict[str, Any]:
    """
    Checks for a Market Structure Shift (MSS) following a liquidity sweep.
    - Bullish MSS: Price breaks above the most recent Lower High after sweeping SSL.
    - Bearish MSS: Price breaks below the most recent Higher Low after sweeping BSL.
    """
    if not sweep_info.get("swept"):
        return {"confirmed": False, "type": None, "broken_level": 0.0}
    
    latest = df.iloc[-1]
    sweep_type = sweep_info.get("type")
    
    if sweep_type == "SSL":
        # Look for prior Lower High to break
        if swing_highs:
            prior_high = swing_highs[-1]["price"]
            if latest['close'] > prior_high:
                return {
                    "confirmed": True,
                    "type": "BULLISH_MSS",
                    "broken_level": prior_high,
                    "invalidation": sweep_info["extreme"]
                }
    elif sweep_type == "BSL":
        # Look for prior Higher Low to break
        if swing_lows:
            prior_low = swing_lows[-1]["price"]
            if latest['close'] < prior_low:
                return {
                    "confirmed": True,
                    "type": "BEARISH_MSS",
                    "broken_level": prior_low,
                    "invalidation": sweep_info["extreme"]
                }
                
    return {"confirmed": False, "type": None, "broken_level": 0.0}
