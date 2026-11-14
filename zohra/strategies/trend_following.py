"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — TREND FOLLOWING STRATEGY             ║
║  Designed for Trending Markets                       ║
║  Uses EMA Alignment + MACD Crossover + ADX Filters   ║
╚══════════════════════════════════════════════════════╝
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict

from zohra.strategies.base import BaseStrategy
from zohra.core.enums import StrategyName, Direction


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend following strategy active in Trending market regimes.
    Signals are generated when moving averages are aligned and we get a MACD cross or EMA pull.
    """

    @classmethod
    def metadata(cls):
        """Structured metadata for the Strategy Registry (Phase 2)."""
        return {
            "name": "trend_following",
            "category": "TrendFollowing",
            "applicable_regimes": ["trending", "strong_trend"],
            "applicable_sessions": ["London", "NewYork", "Overlap"],
            "applicable_timeframes": ["M15", "H1", "H4"],
            "min_rrr": 2.0,
            "description": "EMA Alignment + MACD Crossover + ADX Filters for trend following."
        }

    def __init__(self, ema_fast: int = 20, ema_slow: int = 50, ema_trend: int = 200,
                 adx_threshold: float = 20.0):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.adx_threshold = adx_threshold

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # EMAs
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
        df['ema_trend'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        
        # MACD (12, 26, 9)
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        
        # ADX (14)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        
        plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(14).mean() / (df['atr'] + 1e-9)
        minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(14).mean() / (df['atr'] + 1e-9)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        df['adx'] = dx.rolling(14).mean()
        
        return df

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[dict]:
        """
        Evaluates trend-following signals.
        Returns a signal dict if criteria met, else None.
        """
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return None

        if df is None or len(df) < max(self.ema_trend, 50):
            return None

        df_ind = self.calculate_indicators(df)
        latest = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]
        
        price = latest['close']
        atr = latest['atr']
        
        if pd.isna(latest['ema_trend']) or pd.isna(latest['adx']) or pd.isna(atr):
            return None

        # Confirm strong trend regime via ADX
        if latest['adx'] < self.adx_threshold:
            return None

        # ─── 1. Bullish Trend Following (Buy) ───
        # Alignment: Price > EMA20 > EMA50 > EMA200
        is_bullish_aligned = price > latest['ema_fast'] > latest['ema_slow'] > latest['ema_trend']
        # Trigger: MACD line crosses above signal line OR price pulls back and bounces off EMA20/EMA50
        macd_cross_up = prev['macd'] <= prev['macd_signal'] and latest['macd'] > latest['macd_signal']
        ema_pullback_bounce = prev['low'] <= prev['ema_fast'] and latest['close'] > latest['ema_fast'] and latest['close'] > prev['close']
        
        if is_bullish_aligned and (macd_cross_up or ema_pullback_bounce):
            entry = price
            # Stop Loss at EMA50 or 1.5*ATR below entry
            stop = min(latest['ema_slow'], price - (atr * 1.5))
            # Take Profit at 3.0*ATR (minimum 2:1 R/R)
            tp = price + (price - stop) * 2.0
            
            if tp > entry and entry > stop:
                return {
                    "strategy": StrategyName.TREND_FOLLOWING.value,
                    "symbol": symbol,
                    "direction": Direction.LONG.value,
                    "entry_price": entry,
                    "stop_loss": round(stop, 5),
                    "take_profit": round(tp, 5),
                    "reason": f"Bullish trend follow: ADX={latest['adx']:.1f}, aligned EMAs, trigger={'MACD cross' if macd_cross_up else 'EMA pull'}",
                    "indicators": {
                        "adx": latest['adx'],
                        "ema_fast": latest['ema_fast'],
                        "ema_slow": latest['ema_slow'],
                        "ema_trend": latest['ema_trend']
                    }
                }

        # ─── 2. Bearish Trend Following (Sell) ───
        # Alignment: Price < EMA20 < EMA50 < EMA200
        is_bearish_aligned = price < latest['ema_fast'] < latest['ema_slow'] < latest['ema_trend']
        macd_cross_down = prev['macd'] >= prev['macd_signal'] and latest['macd'] < latest['macd_signal']
        ema_pullback_bounce_short = prev['high'] >= prev['ema_fast'] and latest['close'] < latest['ema_fast'] and latest['close'] < prev['close']
        
        if is_bearish_aligned and (macd_cross_down or ema_pullback_bounce_short):
            entry = price
            # Stop Loss at EMA50 or 1.5*ATR above entry
            stop = max(latest['ema_slow'], price + (atr * 1.5))
            # Take Profit at 3.0*ATR
            tp = price - (stop - price) * 2.0
            
            if tp < entry and entry < stop:
                return {
                    "strategy": StrategyName.TREND_FOLLOWING.value,
                    "symbol": symbol,
                    "direction": Direction.SHORT.value,
                    "entry_price": entry,
                    "stop_loss": round(stop, 5),
                    "take_profit": round(tp, 5),
                    "reason": f"Bearish trend follow: ADX={latest['adx']:.1f}, aligned EMAs, trigger={'MACD cross' if macd_cross_down else 'EMA pull'}",
                    "indicators": {
                        "adx": latest['adx'],
                        "ema_fast": latest['ema_fast'],
                        "ema_slow": latest['ema_slow'],
                        "ema_trend": latest['ema_trend']
                    }
                }

        return None


# Singleton
trend_following_strategy = TrendFollowingStrategy()
