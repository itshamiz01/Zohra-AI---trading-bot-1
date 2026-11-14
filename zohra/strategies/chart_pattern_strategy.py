"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — CHART PATTERN RECOGNITION STRATEGY    ║
║  Designed for Reversal, Continuation & Neutral       ║
║  Patterns with Global Confirmation Stack (GCS)       ║
╚══════════════════════════════════════════════════════╝
"""

import logging
import numpy as np
import pandas as pd
from typing import Optional, Dict, Tuple, List

from zohra.strategies.base import BaseStrategy
from zohra.core.enums import StrategyName, Direction

logger = logging.getLogger("zohra.strategies.chart_pattern")


class ChartPatternStrategy(BaseStrategy):
    """
    Implements rule-based chart pattern recognition logic from the Algorithmic Trading Manual.
    Includes the Global Confirmation Stack (GCS) and n+1 / retest filters.
    """

    @classmethod
    def metadata(cls):
        """Structured metadata for the Strategy Registry (Phase 2)."""
        return {
            "name": "chart_patterns",
            "category": "ChartPattern",
            "applicable_regimes": ["trending", "ranging", "breakout"],
            "applicable_sessions": ["London", "NewYork", "Asian", "Overlap"],
            "applicable_timeframes": ["M15", "H1", "H4"],
            "min_rrr": 2.0,
            "description": "Rule-based pattern recognition for reversal, continuation, and neutral patterns."
        }

    def __init__(self, pivot_window: int = 5, min_rrr: float = 2.0):
        self.pivot_window = pivot_window
        self.min_rrr = min_rrr

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicators needed for GCS and Trend classification."""
        df = df.copy()
        
        # Volume column detection
        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'
        
        # 1. 10-period SMA of Volume
        if vol_col in df.columns:
            df['vol_sma10'] = df[vol_col].rolling(10).mean()
        else:
            df['vol_sma10'] = 1.0  # fallback
            df[vol_col] = 1.0

        # 2. RSI(14)
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi_14'] = 100 - (100 / (1 + rs))

        # 3. MACD(12, 26, 9)
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = df['ema12'] - df['ema26']
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # 4. Trend Indicators: EMA(50) and EMA(200)
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

        # 5. ATR(14)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()

        return df

    def _get_pivots(self, df: pd.DataFrame, window: int = 5) -> List[Dict]:
        """Detect swing high and swing low pivots in the dataframe."""
        pivots = []
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        
        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'
        vols = df[vol_col].values if vol_col in df.columns else np.zeros(len(df))

        for i in range(window, len(df) - window):
            # Swing High Peak
            is_high = True
            for j in range(1, window + 1):
                if highs[i] < highs[i - j] or highs[i] < highs[i + j]:
                    is_high = False
                    break
            if is_high:
                pivots.append({
                    'type': 'high',
                    'index': i,
                    'price': float(highs[i]),
                    'volume': float(vols[i]),
                    'close': float(closes[i])
                })
                continue

            # Swing Low Trough
            is_low = True
            for j in range(1, window + 1):
                if lows[i] > lows[i - j] or lows[i] > lows[i + j]:
                    is_low = False
                    break
            if is_low:
                pivots.append({
                    'type': 'low',
                    'index': i,
                    'price': float(lows[i]),
                    'volume': float(vols[i]),
                    'close': float(closes[i])
                })
        return pivots

    def _detect_double_triple_top(self, df: pd.DataFrame, pivots: List[Dict], trend: str, current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Double / Triple Top detection logic."""
        if trend != "UPTREND":
            return None

        high_pivots = [p for p in pivots if p['type'] == 'high' and p['index'] >= len(df) - 60]
        if len(high_pivots) < 2:
            return None

        # Check Triple Top first
        if len(high_pivots) >= 3:
            p1, p2, p3 = high_pivots[-3], high_pivots[-2], high_pivots[-1]
            var1 = abs(p1['price'] - p2['price']) / current_price
            var2 = abs(p2['price'] - p3['price']) / current_price
            var3 = abs(p1['price'] - p3['price']) / current_price
            if var1 <= 0.04 and var2 <= 0.04 and var3 <= 0.04:
                # Volume declination
                if p1['volume'] > p2['volume']:
                    # Neckline is minimum low between peaks
                    neckline = float(df['low'].iloc[p1['index']:p3['index']+1].min())
                    h = max(p1['price'], p2['price'], p3['price']) - neckline
                    breakout_idx = len(df) - 2
                    if df['close'].iloc[breakout_idx] < neckline:
                        entry = current_price
                        stop = neckline + h
                        tp = neckline - h
                        return ("SHORT", breakout_idx, entry, stop, tp, "Triple Top")

        # Double Top (M-Pattern)
        p1, p2 = high_pivots[-2], high_pivots[-1]
        var = abs(p1['price'] - p2['price']) / current_price
        if var <= 0.04:
            if p1['volume'] > p2['volume']:
                neckline = float(df['low'].iloc[p1['index']:p2['index']+1].min())
                h = max(p1['price'], p2['price']) - neckline
                breakout_idx = len(df) - 2
                if df['close'].iloc[breakout_idx] < neckline:
                    entry = current_price
                    stop = neckline + h
                    tp = neckline - h
                    return ("SHORT", breakout_idx, entry, stop, tp, "Double Top (M-Pattern)")

        return None

    def _detect_double_triple_bottom(self, df: pd.DataFrame, pivots: List[Dict], trend: str, current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Double / Triple Bottom detection logic."""
        if trend != "DOWNTREND":
            return None

        low_pivots = [p for p in pivots if p['type'] == 'low' and p['index'] >= len(df) - 60]
        if len(low_pivots) < 2:
            return None

        # Check Triple Bottom first
        if len(low_pivots) >= 3:
            p1, p2, p3 = low_pivots[-3], low_pivots[-2], low_pivots[-1]
            var1 = abs(p1['price'] - p2['price']) / current_price
            var2 = abs(p2['price'] - p3['price']) / current_price
            var3 = abs(p1['price'] - p3['price']) / current_price
            if var1 <= 0.04 and var2 <= 0.04 and var3 <= 0.04:
                if p1['volume'] > p2['volume']:
                    neckline = float(df['high'].iloc[p1['index']:p3['index']+1].max())
                    h = neckline - min(p1['price'], p2['price'], p3['price'])
                    breakout_idx = len(df) - 2
                    if df['close'].iloc[breakout_idx] > neckline:
                        entry = current_price
                        stop = neckline - h
                        tp = neckline + h
                        return ("LONG", breakout_idx, entry, stop, tp, "Triple Bottom")

        # Double Bottom (W-Pattern)
        p1, p2 = low_pivots[-2], low_pivots[-1]
        var = abs(p1['price'] - p2['price']) / current_price
        if var <= 0.04:
            if p1['volume'] > p2['volume']:
                neckline = float(df['high'].iloc[p1['index']:p2['index']+1].max())
                h = neckline - min(p1['price'], p2['price'])
                breakout_idx = len(df) - 2
                if df['close'].iloc[breakout_idx] > neckline:
                    entry = current_price
                    stop = neckline - h
                    tp = neckline + h
                    return ("LONG", breakout_idx, entry, stop, tp, "Double Bottom (W-Pattern)")

        return None

    def _detect_head_and_shoulders(self, df: pd.DataFrame, pivots: List[Dict], trend: str, current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Head and Shoulders (Standard & Inverse) detection logic."""
        high_pivots = [p for p in pivots if p['type'] == 'high']
        low_pivots = [p for p in pivots if p['type'] == 'low']

        # 1. Standard Head and Shoulders (Bearish Reversal)
        if trend == "UPTREND" and len(high_pivots) >= 3:
            s_l, head, s_r = high_pivots[-3], high_pivots[-2], high_pivots[-1]
            if head['price'] > s_l['price'] and head['price'] > s_r['price']:
                shoulder_var = abs(s_l['price'] - s_r['price']) / current_price
                if shoulder_var <= 0.04:
                    # Troughs
                    t1_idx = s_l['index'] + np.argmin(df['low'].values[s_l['index']:head['index']])
                    t2_idx = head['index'] + np.argmin(df['low'].values[head['index']:s_r['index']])
                    t1_val = df['low'].values[t1_idx]
                    t2_val = df['low'].values[t2_idx]
                    
                    if t2_idx > t1_idx:
                        # Slope of neckline
                        m = (t2_val - t1_val) / (t2_idx - t1_idx)
                        breakout_idx = len(df) - 2
                        neckline_val = t1_val + m * (breakout_idx - t1_idx)
                        
                        if df['close'].iloc[breakout_idx] < neckline_val:
                            entry = current_price
                            stop = s_r['price']
                            tp1 = neckline_val - (s_l['price'] - neckline_val)
                            tp2 = neckline_val - (head['price'] - neckline_val)
                            return ("SHORT", breakout_idx, entry, stop, tp2, "Standard Head and Shoulders")

        # 2. Inverse Head and Shoulders (Bullish Reversal)
        if trend == "DOWNTREND" and len(low_pivots) >= 3:
            s_l, head, s_r = low_pivots[-3], low_pivots[-2], low_pivots[-1]
            if head['price'] < s_l['price'] and head['price'] < s_r['price']:
                shoulder_var = abs(s_l['price'] - s_r['price']) / current_price
                if shoulder_var <= 0.04:
                    # Peaks
                    t1_idx = s_l['index'] + np.argmax(df['high'].values[s_l['index']:head['index']])
                    t2_idx = head['index'] + np.argmax(df['high'].values[head['index']:s_r['index']])
                    t1_val = df['high'].values[t1_idx]
                    t2_val = df['high'].values[t2_idx]
                    
                    if t2_idx > t1_idx:
                        m = (t2_val - t1_val) / (t2_idx - t1_idx)
                        breakout_idx = len(df) - 2
                        neckline_val = t1_val + m * (breakout_idx - t1_idx)
                        
                        if df['close'].iloc[breakout_idx] > neckline_val:
                            entry = current_price
                            stop = s_r['price']
                            tp1 = neckline_val + (neckline_val - s_l['price'])
                            tp2 = neckline_val + (neckline_val - head['price'])
                            return ("LONG", breakout_idx, entry, stop, tp2, "Inverse Head and Shoulders")

        return None

    def _detect_wedges(self, df: pd.DataFrame, pivots: List[Dict], trend: str, current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Rising and Falling Wedges detection logic using regression slopes."""
        high_pivots = [p for p in pivots if p['type'] == 'high'][-4:]
        low_pivots = [p for p in pivots if p['type'] == 'low'][-4:]

        if len(high_pivots) < 3 or len(low_pivots) < 3:
            return None

        # Regression for Highs boundary
        x_high = [p['index'] for p in high_pivots]
        y_high = [p['price'] for p in high_pivots]
        slope_high, intercept_high = np.polyfit(x_high, y_high, 1)

        # Regression for Lows boundary
        x_low = [p['index'] for p in low_pivots]
        y_low = [p['price'] for p in low_pivots]
        slope_low, intercept_low = np.polyfit(x_low, y_low, 1)

        breakout_idx = len(df) - 2

        # 1. Rising Wedge (Bearish Reversal in Uptrend)
        if trend == "UPTREND" and slope_low > slope_high > 0:
            lower_boundary = slope_low * breakout_idx + intercept_low
            upper_boundary = slope_high * breakout_idx + intercept_high
            
            if df['close'].iloc[breakout_idx] < lower_boundary:
                entry = current_price
                stop = upper_boundary
                tp = lower_boundary - (upper_boundary - lower_boundary) * 2.0
                return ("SHORT", breakout_idx, entry, stop, tp, "Rising Wedge")

        # 2. Falling Wedge (Bullish Reversal in Downtrend)
        if trend == "DOWNTREND" and slope_high < slope_low < 0:
            upper_boundary = slope_high * breakout_idx + intercept_high
            lower_boundary = slope_low * breakout_idx + intercept_low
            
            if df['close'].iloc[breakout_idx] > upper_boundary:
                entry = current_price
                stop = lower_boundary
                tp = upper_boundary + (upper_boundary - lower_boundary) * 2.0
                return ("LONG", breakout_idx, entry, stop, tp, "Falling Wedge")

        return None

    def _detect_expanding_triangles(self, df: pd.DataFrame, pivots: List[Dict], current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Expanding Triangles breakout logic."""
        high_pivots = [p for p in pivots if p['type'] == 'high'][-3:]
        low_pivots = [p for p in pivots if p['type'] == 'low'][-3:]

        if len(high_pivots) < 2 or len(low_pivots) < 2:
            return None

        # Check expanding conditions (Highs getting higher, Lows getting lower)
        if high_pivots[-1]['price'] > high_pivots[-2]['price'] and low_pivots[-1]['price'] < low_pivots[-2]['price']:
            x_high = [p['index'] for p in high_pivots]
            y_high = [p['price'] for p in high_pivots]
            slope_high, intercept_high = np.polyfit(x_high, y_high, 1)

            x_low = [p['index'] for p in low_pivots]
            y_low = [p['price'] for p in low_pivots]
            slope_low, intercept_low = np.polyfit(x_low, y_low, 1)

            breakout_idx = len(df) - 2
            upper_boundary = slope_high * breakout_idx + intercept_high
            lower_boundary = slope_low * breakout_idx + intercept_low

            # Bullish Breakout
            if df['close'].iloc[breakout_idx] > upper_boundary:
                entry = current_price
                stop = low_pivots[-1]['price']
                tp = upper_boundary + (upper_boundary - lower_boundary) * 1.5
                return ("LONG", breakout_idx, entry, stop, tp, "Expanding Triangle (Bullish Breakout)")

            # Bearish Breakout
            if df['close'].iloc[breakout_idx] < lower_boundary:
                entry = current_price
                stop = high_pivots[-1]['price']
                tp = lower_boundary - (upper_boundary - lower_boundary) * 1.5
                return ("SHORT", breakout_idx, entry, stop, tp, "Expanding Triangle (Bearish Breakout)")

        return None

    def _detect_rectangles(self, df: pd.DataFrame, pivots: List[Dict], trend: str, current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Bullish & Bearish Rectangles detection logic."""
        high_pivots = [p for p in pivots if p['type'] == 'high'][-3:]
        low_pivots = [p for p in pivots if p['type'] == 'low'][-3:]

        if len(high_pivots) < 2 or len(low_pivots) < 2:
            return None

        # Touches check: Highs and Lows are parallel/horizontal within 1% price variance
        highs_near = abs(high_pivots[-1]['price'] - high_pivots[-2]['price']) / current_price <= 0.01
        lows_near = abs(low_pivots[-1]['price'] - low_pivots[-2]['price']) / current_price <= 0.01

        if highs_near and lows_near:
            resistance = (high_pivots[-1]['price'] + high_pivots[-2]['price']) / 2.0
            support = (low_pivots[-1]['price'] + low_pivots[-2]['price']) / 2.0
            h = resistance - support
            breakout_idx = len(df) - 2

            # Bullish Rectangle (Continuation in Uptrend)
            if trend == "UPTREND" and df['close'].iloc[breakout_idx] > resistance:
                entry = current_price
                stop = entry - 0.5 * h
                tp = entry + h
                return ("LONG", breakout_idx, entry, stop, tp, "Bullish Rectangle")

            # Bearish Rectangle (Continuation in Downtrend)
            if trend == "DOWNTREND" and df['close'].iloc[breakout_idx] < support:
                entry = current_price
                stop = entry + 0.5 * h
                tp = entry - h
                return ("SHORT", breakout_idx, entry, stop, tp, "Bearish Rectangle")

        return None

    def _detect_flags_pennants(self, df: pd.DataFrame, pivots: List[Dict], trend: str, current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Flags and Pennants detection logic."""
        # Find a high-momentum impulse pole move (pole_height >= 1.5 * ATR over last 15-20 bars)
        atr = df['atr'].iloc[-1]
        if pd.isna(atr) or atr <= 0:
            return None

        lookback = 15
        if len(df) < lookback + 5:
            return None

        # Find absolute max swing height in recent lookback
        price_slice = df['close'].tail(lookback)
        max_p = price_slice.max()
        min_p = price_slice.min()
        pole_height = max_p - min_p

        if pole_height < 2.0 * atr:
            return None

        high_pivots = [p for p in pivots if p['type'] == 'high'][-3:]
        low_pivots = [p for p in pivots if p['type'] == 'low'][-3:]

        if len(high_pivots) < 2 or len(low_pivots) < 2:
            return None

        breakout_idx = len(df) - 2

        # Symmetrical contraction for Pennants, or parallel slope for Flags
        # 1. Bullish Flag / Pennant (Continuation in Uptrend)
        if trend == "UPTREND":
            resistance = high_pivots[-1]['price']
            support = low_pivots[-1]['price']
            if df['close'].iloc[breakout_idx] > resistance:
                entry = current_price
                stop = support
                tp = entry + pole_height
                return ("LONG", breakout_idx, entry, stop, tp, "Bullish Flag/Pennant")

        # 2. Bearish Flag / Pennant (Continuation in Downtrend)
        if trend == "DOWNTREND":
            resistance = high_pivots[-1]['price']
            support = low_pivots[-1]['price']
            if df['close'].iloc[breakout_idx] < support:
                entry = current_price
                stop = resistance
                tp = entry - pole_height
                return ("SHORT", breakout_idx, entry, stop, tp, "Bearish Flag/Pennant")

        return None

    def _detect_cup_and_handle(self, df: pd.DataFrame, pivots: List[Dict], trend: str, current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Cup and Handle (Standard & Inverse) logic with rounding checks."""
        # Find U-shape cup: rounded recovery
        # 1. Standard Cup and Handle
        if trend == "UPTREND" and len(df) >= 40:
            # We look for a deep cup (trough) followed by a shallow retrace (handle)
            # Find the local peaks and troughs in the last 40 bars
            slice_highs = df['high'].tail(40).values
            slice_lows = df['low'].tail(40).values
            
            # Cup left rim peak, cup bottom trough, cup right rim peak
            left_rim_idx = np.argmax(slice_highs[:15])
            right_rim_idx = 15 + np.argmax(slice_highs[15:30])
            cup_bottom_idx = left_rim_idx + np.argmin(slice_lows[left_rim_idx:right_rim_idx])
            
            cup_depth = max(slice_highs[left_rim_idx], slice_highs[right_rim_idx]) - slice_lows[cup_bottom_idx]
            if cup_depth <= 0:
                return None

            # Discard V-shape check: Bottom must be rounded (spending time near bottom)
            bottom_zone = slice_lows[cup_bottom_idx] + 0.25 * cup_depth
            cup_duration = right_rim_idx - left_rim_idx
            if cup_duration <= 5:
                return None
            
            bars_in_bottom = sum(1 for low in slice_lows[left_rim_idx:right_rim_idx] if low <= bottom_zone)
            if (bars_in_bottom / cup_duration) < 0.30:
                # Too V-shaped
                return None

            # Handle retrace check (must form between right rim and current)
            handle_low = np.min(slice_lows[right_rim_idx:])
            handle_retrace = slice_highs[right_rim_idx] - handle_low
            
            if 0.33 * cup_depth <= handle_retrace <= 0.50 * cup_depth:
                # Trigger breakout of the handle resistance
                resistance_level = slice_highs[right_rim_idx]
                breakout_idx = len(df) - 2
                if df['close'].iloc[breakout_idx] > resistance_level:
                    entry = current_price
                    stop = handle_low
                    tp = entry + cup_depth
                    return ("LONG", breakout_idx, entry, stop, tp, "Standard Cup and Handle")

        # 2. Reverse Cup and Handle
        if trend == "DOWNTREND" and len(df) >= 40:
            slice_highs = df['high'].tail(40).values
            slice_lows = df['low'].tail(40).values
            
            left_rim_idx = np.argmin(slice_lows[:15])
            right_rim_idx = 15 + np.argmin(slice_lows[15:30])
            cup_bottom_idx = left_rim_idx + np.argmax(slice_highs[left_rim_idx:right_rim_idx])
            
            cup_depth = slice_highs[cup_bottom_idx] - min(slice_lows[left_rim_idx], slice_lows[right_rim_idx])
            if cup_depth <= 0:
                return None

            bottom_zone = slice_highs[cup_bottom_idx] - 0.25 * cup_depth
            cup_duration = right_rim_idx - left_rim_idx
            if cup_duration <= 5:
                return None
            
            bars_in_bottom = sum(1 for high in slice_highs[left_rim_idx:right_rim_idx] if high >= bottom_zone)
            if (bars_in_bottom / cup_duration) < 0.30:
                return None

            handle_high = np.max(slice_highs[right_rim_idx:])
            handle_retrace = handle_high - slice_lows[right_rim_idx]
            
            if 0.33 * cup_depth <= handle_retrace <= 0.50 * cup_depth:
                support_level = slice_lows[right_rim_idx]
                breakout_idx = len(df) - 2
                if df['close'].iloc[breakout_idx] < support_level:
                    entry = current_price
                    stop = handle_high
                    tp = entry - cup_depth
                    return ("SHORT", breakout_idx, entry, stop, tp, "Reverse Cup and Handle")

        return None

    def _detect_triangles(self, df: pd.DataFrame, pivots: List[Dict], current_price: float) -> Optional[Tuple[str, int, float, float, float, str]]:
        """Ascending, Descending & Symmetrical Triangles detection logic."""
        high_pivots = [p for p in pivots if p['type'] == 'high'][-3:]
        low_pivots = [p for p in pivots if p['type'] == 'low'][-3:]

        if len(high_pivots) < 2 or len(low_pivots) < 2:
            return None

        x_high = [p['index'] for p in high_pivots]
        y_high = [p['price'] for p in high_pivots]
        slope_high, intercept_high = np.polyfit(x_high, y_high, 1)

        x_low = [p['index'] for p in low_pivots]
        y_low = [p['price'] for p in low_pivots]
        slope_low, intercept_low = np.polyfit(x_low, y_low, 1)

        # Intersection point (Apex)
        if abs(slope_high - slope_low) > 1e-9:
            apex_x = (intercept_low - intercept_high) / (slope_high - slope_low)
            apex_y = slope_high * apex_x + intercept_high
        else:
            apex_y = current_price

        breakout_idx = len(df) - 2
        upper_boundary = slope_high * breakout_idx + intercept_high
        lower_boundary = slope_low * breakout_idx + intercept_low
        triangle_width = upper_boundary - lower_boundary

        # Determine pattern type based on slopes
        is_ascending = abs(slope_high) < 1e-3 and slope_low > 1e-3
        is_descending = abs(slope_low) < 1e-3 and slope_high < -1e-3
        is_symmetrical = slope_high < -1e-3 and slope_low > 1e-3

        # 1. Ascending Triangle
        if is_ascending:
            if df['close'].iloc[breakout_idx] > upper_boundary:
                return ("LONG", breakout_idx, current_price, apex_y, current_price + triangle_width, "Ascending Triangle Breakout Up")
            if df['close'].iloc[breakout_idx] < lower_boundary:
                return ("SHORT", breakout_idx, current_price, apex_y, current_price - triangle_width, "Ascending Triangle Breakout Down")

        # 2. Descending Triangle
        if is_descending:
            if df['close'].iloc[breakout_idx] < lower_boundary:
                return ("SHORT", breakout_idx, current_price, apex_y, current_price - triangle_width, "Descending Triangle Breakout Down")
            if df['close'].iloc[breakout_idx] > upper_boundary:
                return ("LONG", breakout_idx, current_price, apex_y, current_price + triangle_width, "Descending Triangle Breakout Up")

        # 3. Symmetrical Triangle
        if is_symmetrical:
            if df['close'].iloc[breakout_idx] > upper_boundary:
                return ("LONG", breakout_idx, current_price, apex_y, current_price + triangle_width, "Symmetrical Triangle Breakout Up")
            if df['close'].iloc[breakout_idx] < lower_boundary:
                return ("SHORT", breakout_idx, current_price, apex_y, current_price - triangle_width, "Symmetrical Triangle Breakout Down")

        return None

    def _validate_rsi_divergence(self, df: pd.DataFrame, direction: str) -> bool:
        """Verify if there is momentum divergence against trade direction."""
        # 14-bar RSI
        rsi = df['rsi_14'].values
        closes = df['close'].values
        
        # Bullish Divergence check (for Short Entry - we reject Short if there's bullish divergence)
        if direction == "SHORT":
            # Price makes lower low, RSI makes higher low
            recent_lows = df['low'].tail(20).values
            recent_rsi = df['rsi_14'].tail(20).values
            if len(recent_lows) >= 10:
                p_low1_idx = np.argmin(recent_lows[:10])
                p_low2_idx = 10 + np.argmin(recent_lows[10:])
                if recent_lows[p_low2_idx] < recent_lows[p_low1_idx]:
                    if recent_rsi[p_low2_idx] > recent_rsi[p_low1_idx] + 2:
                        return False # Divergence detected, reject Short

        # Bearish Divergence check (for Long Entry - we reject Long if there's bearish divergence)
        if direction == "LONG":
            # Price makes higher high, RSI makes lower high
            recent_highs = df['high'].tail(20).values
            recent_rsi = df['rsi_14'].tail(20).values
            if len(recent_highs) >= 10:
                p_high1_idx = np.argmax(recent_highs[:10])
                p_high2_idx = 10 + np.argmax(recent_highs[10:])
                if recent_highs[p_high2_idx] > recent_highs[p_high1_idx]:
                    if recent_rsi[p_high2_idx] < recent_rsi[p_high1_idx] - 2:
                        return False # Divergence detected, reject Long

        return True

    def _validate_gcs(self, df: pd.DataFrame, direction: str, breakout_idx: int) -> bool:
        """Global Confirmation Stack validation."""
        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'

        # 1. Volume confirmation
        breakout_vol = df[vol_col].iloc[breakout_idx]
        avg_vol = df['vol_sma10'].iloc[breakout_idx]
        if pd.isna(breakout_vol) or pd.isna(avg_vol) or breakout_vol <= avg_vol:
            return False

        # 2. RSI alignment & divergence
        rsi_val = df['rsi_14'].iloc[-1]
        if pd.isna(rsi_val):
            return False

        if direction == "LONG" and rsi_val <= 50:
            return False
        if direction == "SHORT" and rsi_val >= 50:
            return False

        if not self._validate_rsi_divergence(df, direction):
            return False

        # 3. MACD crossover direction confirmation
        macd_val = df['macd'].iloc[-1]
        signal_val = df['macd_signal'].iloc[-1]
        if pd.isna(macd_val) or pd.isna(signal_val):
            return False

        if direction == "LONG" and macd_val <= signal_val:
            return False
        if direction == "SHORT" and macd_val >= signal_val:
            return False

        return True

    def _validate_filters(self, df: pd.DataFrame, direction: str, breakout_idx: int, stop_loss: float, entry_price: float) -> bool:
        """Check n+1 confirmation, Retest-Bounce, and RRR rules."""
        latest_idx = len(df) - 1

        # 1. n+1 Confirmation Rule
        n_plus_1_confirmed = False
        if direction == "LONG":
            if df['high'].iloc[latest_idx] > df['high'].iloc[breakout_idx]:
                n_plus_1_confirmed = True
        else:
            if df['low'].iloc[latest_idx] < df['low'].iloc[breakout_idx]:
                n_plus_1_confirmed = True

        # 2. Retest-Bounce logic fallback
        retest_confirmed = False
        breakout_level = df['close'].iloc[breakout_idx]
        atr = df['atr'].iloc[latest_idx]
        if pd.isna(atr):
            atr = 0.001

        if direction == "LONG":
            # Price pulls back close to breakout level and bounces bullish
            pulled_back = df['low'].iloc[latest_idx] <= breakout_level + 0.2 * atr
            bounced = df['close'].iloc[latest_idx] > df['open'].iloc[latest_idx]
            if pulled_back and bounced:
                retest_confirmed = True
        else:
            # Price pulls back close to breakout level and bounces bearish
            pulled_back = df['high'].iloc[latest_idx] >= breakout_level - 0.2 * atr
            bounced = df['close'].iloc[latest_idx] < df['open'].iloc[latest_idx]
            if pulled_back and bounced:
                retest_confirmed = True

        if not (n_plus_1_confirmed or retest_confirmed):
            return False

        # 3. Risk-Reward Ratio (RRR) Check
        # If stop_loss calculation is invalid, fallback
        if direction == "LONG" and entry_price <= stop_loss:
            return False
        if direction == "SHORT" and entry_price >= stop_loss:
            return False

        return True

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[dict]:
        """Runs the multi-pattern detection pipeline and returns signals."""
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return None

        if df is None or len(df) < 55:
            return None

        # Compute indicators
        df_ind = self.calculate_indicators(df)
        latest = df_ind.iloc[-1]
        
        current_price = float(latest['close'])
        
        # Determine Trend context
        trend = "NEUTRAL"
        if latest['close'] > latest['ema50'] and latest['ema50'] > latest['ema200']:
            trend = "UPTREND"
        elif latest['close'] < latest['ema50'] and latest['ema50'] < latest['ema200']:
            trend = "DOWNTREND"

        # Detect pivots
        pivots = self._get_pivots(df_ind, window=self.pivot_window)
        if not pivots:
            return None

        # Pattern evaluation list
        detectors = [
            self._detect_double_triple_top,
            self._detect_double_triple_bottom,
            self._detect_head_and_shoulders,
            self._detect_wedges,
            self._detect_expanding_triangles,
            self._detect_rectangles,
            self._detect_flags_pennants,
            self._detect_cup_and_handle,
            self._detect_triangles
        ]

        # Scan each detector
        for detector in detectors:
            try:
                res = None
                if detector.__name__ in ('_detect_expanding_triangles', '_detect_triangles'):
                    res = detector(df_ind, pivots, current_price)
                else:
                    res = detector(df_ind, pivots, trend, current_price)

                if res:
                    direction, breakout_idx, entry, stop, tp, pattern_name = res
                    
                    # RRR calculation
                    if direction == "LONG":
                        rrr = (tp - entry) / (entry - stop + 1e-9)
                    else:
                        rrr = (entry - tp) / (stop - entry + 1e-9)
                    
                    if rrr < self.min_rrr:
                        continue

                    # Validate GCS & execution rules
                    if self._validate_gcs(df_ind, direction, breakout_idx) and \
                       self._validate_filters(df_ind, direction, breakout_idx, stop, entry):
                        
                        return {
                            "strategy": StrategyName.CHART_PATTERNS.value,
                            "symbol": symbol,
                            "direction": direction,
                            "entry_price": round(entry, 5),
                            "stop_loss": round(stop, 5),
                            "take_profit": round(tp, 5),
                            "reason": f"Chart pattern breakout: detected {pattern_name} with confirmed GCS stack. RRR={rrr:.2f}",
                            "indicators": {
                                "rsi": float(latest['rsi_14']),
                                "macd": float(latest['macd']),
                                "atr": float(latest['atr'])
                            }
                        }
            except Exception as e:
                logger.error(f"Error executing chart pattern detector {detector.__name__}: {e}")

        return None


# Singleton instance
chart_pattern_strategy = ChartPatternStrategy()
