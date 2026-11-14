"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — MEAN REVERSION STRATEGY              ║
║  Designed for Ranging Markets                        ║
║  Uses Bollinger Bands + RSI Reversals + Pivots       ║
╚══════════════════════════════════════════════════════╝
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict

from zohra.strategies.base import BaseStrategy
from zohra.core.enums import StrategyName, Direction


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion strategy active in Ranging market regimes.
    Signals are generated when price reaches BB extremes combined with RSI exhaustion.
    """

    @classmethod
    def metadata(cls):
        """Structured metadata for the Strategy Registry (Phase 2)."""
        return {
            "name": "mean_reversion",
            "category": "MeanReversion",
            "applicable_regimes": ["ranging", "low_volatility", "consolidation"],
            "applicable_sessions": ["London", "NewYork", "Asian", "Overlap"],
            "applicable_timeframes": ["M5", "M15", "H1"],
            "min_rrr": 1.5,
            "description": "Bollinger Bands + RSI Reversals + Pivots for ranging markets."
        }

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0, rsi_period: int = 14,
                 rsi_overbought: float = 70.0, rsi_oversold: float = 30.0):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Bollinger Bands
        sma = df['close'].rolling(self.bb_period).mean()
        std = df['close'].rolling(self.bb_period).std()
        df['bb_mid'] = sma
        df['bb_upper'] = sma + (std * self.bb_std)
        df['bb_lower'] = sma - (std * self.bb_std)
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.rsi_period).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Local Pivots (lookback 20)
        df['pivot_high'] = df['high'].rolling(20).max()
        df['pivot_low'] = df['low'].rolling(20).min()
        
        # ATR (for SL/TP scaling)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
        
        return df

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[dict]:
        """
        Evaluates ranging signals.
        Returns a signal dict if criteria met, else None.
        """
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return None

        if df is None or len(df) < max(self.bb_period, self.rsi_period, 50):
            return None

        df_ind = self.calculate_indicators(df)
        latest = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]
        
        price = latest['close']
        atr = latest['atr']
        
        if pd.isna(latest['bb_upper']) or pd.isna(latest['rsi']) or pd.isna(atr):
            return None

        # ─── 1. Bullish Mean Reversion (Buy at range bottom) ───
        # Criteria: Price crossed below or touched BB lower band, and RSI is oversold (< 30) or turning up
        is_touching_lower = price <= latest['bb_lower'] or prev['close'] <= prev['bb_lower']
        rsi_oversold_trigger = latest['rsi'] < self.rsi_oversold or (prev['rsi'] < self.rsi_oversold and latest['rsi'] > prev['rsi'])
        
        if is_touching_lower and rsi_oversold_trigger:
            entry = price
            # SL below local pivot low or 2*ATR
            stop = min(latest['pivot_low'] - (atr * 0.5), price - (atr * 2.0))
            # TP at BB upper band or BB mid depending on risk
            tp = latest['bb_mid']  # First target is middle of range
            
            # Ensure positive risk-reward
            if tp > entry and entry > stop:
                return {
                    "strategy": StrategyName.MEAN_REVERSION.value,
                    "symbol": symbol,
                    "direction": Direction.LONG.value,
                    "entry_price": entry,
                    "stop_loss": round(stop, 5),
                    "take_profit": round(tp, 5),
                    "reason": f"Bullish mean reversion: RSI={latest['rsi']:.1f} oversold, price={price:.5f} near BB lower={latest['bb_lower']:.5f}",
                    "indicators": {
                        "rsi": latest['rsi'],
                        "bb_upper": latest['bb_upper'],
                        "bb_lower": latest['bb_lower'],
                        "bb_mid": latest['bb_mid']
                    }
                }

        # ─── 2. Bearish Mean Reversion (Sell at range top) ───
        # Criteria: Price crossed above or touched BB upper band, and RSI is overbought (> 70) or turning down
        is_touching_upper = price >= latest['bb_upper'] or prev['close'] >= prev['bb_upper']
        rsi_overbought_trigger = latest['rsi'] > self.rsi_overbought or (prev['rsi'] > self.rsi_overbought and latest['rsi'] < prev['rsi'])
        
        if is_touching_upper and rsi_overbought_trigger:
            entry = price
            # SL above local pivot high or 2*ATR
            stop = max(latest['pivot_high'] + (atr * 0.5), price + (atr * 2.0))
            # TP at BB lower band or BB mid
            tp = latest['bb_mid']
            
            if tp < entry and entry < stop:
                return {
                    "strategy": StrategyName.MEAN_REVERSION.value,
                    "symbol": symbol,
                    "direction": Direction.SHORT.value,
                    "entry_price": entry,
                    "stop_loss": round(stop, 5),
                    "take_profit": round(tp, 5),
                    "reason": f"Bearish mean reversion: RSI={latest['rsi']:.1f} overbought, price={price:.5f} near BB upper={latest['bb_upper']:.5f}",
                    "indicators": {
                        "rsi": latest['rsi'],
                        "bb_upper": latest['bb_upper'],
                        "bb_lower": latest['bb_lower'],
                        "bb_mid": latest['bb_mid']
                    }
                }

        return None


# Singleton
mean_reversion_strategy = MeanReversionStrategy()
