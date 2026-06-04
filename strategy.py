"""
Trading Strategy: Dual EMA Crossover + ATR Filter
1H timeframe only.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple
from config import EMA_FAST, EMA_SLOW, ATR_PERIOD, ATR_MINIMUM

class EMA_ATR_Strategy:
    """
    Dual EMA crossover with ATR-based stops and trend filter.

    LONG Entry:
        - Fast EMA crosses above Slow EMA
        - ATR > minimum threshold
        - Price above both EMAs (trend confirmation)

    SHORT Entry:
        - Fast EMA crosses below Slow EMA  
        - ATR > minimum threshold
        - Price below both EMAs (trend confirmation)

    Exit: Stop loss, take profit, or trailing stop.
    """

    def __init__(self):
        self.name = "EMA_ATR_Crossover"

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add EMA and ATR columns to DataFrame"""
        if len(df) < EMA_SLOW + ATR_PERIOD:
            return df

        # EMAs
        df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

        # ATR (Average True Range)
        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = abs(df["high"] - df["close"].shift(1))
        df["tr3"] = abs(df["low"] - df["close"].shift(1))
        df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
        df["atr"] = df["tr"].rolling(window=ATR_PERIOD).mean()

        # EMA crossover signal
        df["ema_diff"] = df["ema_fast"] - df["ema_slow"]
        df["cross_up"] = (df["ema_diff"] > 0) & (df["ema_diff"].shift(1) <= 0)
        df["cross_down"] = (df["ema_diff"] < 0) & (df["ema_diff"].shift(1) >= 0)

        # Trend confirmation
        df["above_both"] = (df["close"] > df["ema_fast"]) & (df["close"] > df["ema_slow"])
        df["below_both"] = (df["close"] < df["ema_fast"]) & (df["close"] < df["ema_slow"])

        # ATR filter
        df["atr_valid"] = df["atr"] >= ATR_MINIMUM

        return df

    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Check latest candle for trade signal.
        Returns signal dict or None.
        """
        df = self.calculate_indicators(df)

        if len(df) < 2:
            return None

        latest = df.iloc[-1]

        # Skip if ATR too low (choppy market)
        if not latest["atr_valid"]:
            return None

        signal = None

        # LONG signal
        if latest["cross_up"] and latest["above_both"]:
            signal = {
                "direction": "LONG",
                "entry": latest["close"],
                "stop": latest["close"] - (latest["atr"] * 1.5),
                "target": latest["close"] + (latest["atr"] * 3.0),
                "atr": latest["atr"],
                "ema_fast": latest["ema_fast"],
                "ema_slow": latest["ema_slow"]
            }

        # SHORT signal
        elif latest["cross_down"] and latest["below_both"]:
            signal = {
                "direction": "SHORT",
                "entry": latest["close"],
                "stop": latest["close"] + (latest["atr"] * 1.5),
                "target": latest["close"] - (latest["atr"] * 3.0),
                "atr": latest["atr"],
                "ema_fast": latest["ema_fast"],
                "ema_slow": latest["ema_slow"]
            }

        return signal

    def check_exit(self, df: pd.DataFrame, position: Dict) -> Optional[Dict]:
        """
        Check if open position should be closed.
        Returns exit dict with reason or None.
        """
        if len(df) < 1:
            return None

        df = self.calculate_indicators(df)

        latest = df.iloc[-1]
        current_price = latest["close"]
        entry_time = pd.to_datetime(position["timestamp_open"])
        current_time = latest.name if isinstance(latest.name, pd.Timestamp) else pd.to_datetime("now")
        hours_held = (current_time - entry_time).total_seconds() / 3600

        direction = position["direction"]
        entry = position["entry_price"]
        stop = position["stop_price"]
        target = position["target_price"]
        atr = position.get("atr", 0.001)

        exit_info = None

        # 1. Hard stop loss
        if direction == "LONG" and current_price <= stop:
            exit_info = {"price": current_price, "reason": "STOP_LOSS"}
        elif direction == "SHORT" and current_price >= stop:
            exit_info = {"price": current_price, "reason": "STOP_LOSS"}

        # 2. Take profit
        elif direction == "LONG" and current_price >= target:
            exit_info = {"price": current_price, "reason": "TAKE_PROFIT"}
        elif direction == "SHORT" and current_price <= target:
            exit_info = {"price": current_price, "reason": "TAKE_PROFIT"}

        # 3. Time stop (5 days max)
        elif hours_held >= 120:
            exit_info = {"price": current_price, "reason": "TIME_STOP"}

        # 4. Trailing stop (move to breakeven, then trail)
        # Check if we should update stop
        elif direction == "LONG":
            # Move to BE at +1x ATR
            be_level = entry + atr
            trail_level = current_price - (atr * 1.5)

            if current_price > be_level and stop < entry:
                # Update to breakeven
                exit_info = {"price": current_price, "reason": "TRAIL_UPDATE", 
                            "new_stop": entry + 0.0001}
            elif current_price > be_level + atr and trail_level > stop:
                # Trail the stop
                exit_info = {"price": current_price, "reason": "TRAIL_UPDATE",
                            "new_stop": trail_level}

        elif direction == "SHORT":
            be_level = entry - atr
            trail_level = current_price + (atr * 1.5)

            if current_price < be_level and stop > entry:
                exit_info = {"price": current_price, "reason": "TRAIL_UPDATE",
                            "new_stop": entry - 0.0001}
            elif current_price < be_level - atr and trail_level < stop:
                exit_info = {"price": current_price, "reason": "TRAIL_UPDATE",
                            "new_stop": trail_level}

        # 5. Reverse signal (optional - close on opposite crossover)
        if latest["cross_down"] and direction == "LONG":
            exit_info = {"price": current_price, "reason": "REVERSE_SIGNAL"}
        elif latest["cross_up"] and direction == "SHORT":
            exit_info = {"price": current_price, "reason": "REVERSE_SIGNAL"}

        return exit_info

    def format_signal_reason(self, signal: Dict) -> str:
        """Human-readable signal explanation"""
        direction = signal["direction"]
        entry = signal["entry"]
        stop = signal["stop"]
        target = signal["target"]
        atr = signal["atr"]

        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0

        return (
            f"📊 {direction} Signal\n"
            f"Entry: {entry:.5f}\n"
            f"Stop: {stop:.5f} (Risk: ${risk:.5f})\n"
            f"Target: {target:.5f} (Reward: ${reward:.5f})\n"
            f"R/R Ratio: {rr:.1f}:1\n"
            f"ATR: {atr:.5f}"
        )

# Singleton instance
strategy = EMA_ATR_Strategy()
