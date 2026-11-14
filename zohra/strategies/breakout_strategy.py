"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — BREAKOUT STRATEGY                    ║
║  Designed for Breakout & Volatility Expansion        ║
║  Uses BB Squeeze-Expansion + ATR + Volume Filter    ║
╚══════════════════════════════════════════════════════╝
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict

from zohra.strategies.base import BaseStrategy
from zohra.core.enums import StrategyName, Direction


class BreakoutStrategy(BaseStrategy):
    """
    Breakout strategy active in Breakout / Volatility Expansion market regimes.
    Signals are triggered when the Bollinger Band width expands after a squeeze and price crosses the boundary.
    """

    @classmethod
    def metadata(cls):
        """Structured metadata for the Strategy Registry (Phase 2)."""
        return {
            "name": "breakout",
            "category": "Breakout",
            "applicable_regimes": ["breakout", "volatile", "volatility_expansion"],
            "applicable_sessions": ["London", "NewYork", "Overlap"],
            "applicable_timeframes": ["M15", "H1", "H4"],
            "min_rrr": 2.0,
            "description": "BB Squeeze-Expansion + ATR + Volume Filter for volatility breakouts."
        }

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0, squeeze_threshold_pct: float = 1.5):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_threshold_pct = squeeze_threshold_pct

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Bollinger Bands
        sma = df['close'].rolling(self.bb_period).mean()
        std = df['close'].rolling(self.bb_period).std()
        df['bb_mid'] = sma
        df['bb_upper'] = sma + (std * self.bb_std)
        df['bb_lower'] = sma - (std * self.bb_std)
        df['bb_width'] = ((df['bb_upper'] - df['bb_lower']) / (sma + 1e-9)) * 100
        
        # Volume SMA
        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'
        if vol_col in df.columns:
            df['vol_sma'] = df[vol_col].rolling(20).mean()
            df['volume_ratio'] = df[vol_col] / (df['vol_sma'] + 1e-9)
        else:
            df['volume_ratio'] = 1.0  # fallback
            
        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
        
        return df

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[dict]:
        """
        Evaluates breakout setups.
        Returns a signal dict if criteria met, else None.
        """
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return None

        if df is None or len(df) < max(self.bb_period, 40):
            return None

        df_ind = self.calculate_indicators(df)
        latest = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]
        
        price = latest['close']
        atr = latest['atr']
        
        if pd.isna(latest['bb_upper']) or pd.isna(latest['bb_width']) or pd.isna(atr):
            return None

        # Squeeze check: look back 5-15 bars for a squeeze (narrow bands)
        recent_min_width = df_ind['bb_width'].tail(15).min()
        is_squeezed = recent_min_width < self.squeeze_threshold_pct
        
        # Expansion check: band width expanding
        is_expanding = latest['bb_width'] > prev['bb_width'] * 1.15
        
        # Volume confirmation
        volume_confirmed = latest['volume_ratio'] >= 1.3
        
        if not (is_squeezed and is_expanding and volume_confirmed):
            return None

        # ─── 1. Bullish Breakout (Buy) ───
        # Price crossed above upper Bollinger Band
        price_break_up = price >= latest['bb_upper'] or prev['close'] >= prev['bb_upper']
        
        if price_break_up:
            entry = price
            # SL inside the range, e.g. at the BB middle band or 1.5*ATR
            stop = min(latest['bb_mid'], price - (atr * 1.5))
            tp = price + (price - stop) * 2.5  # 2.5:1 R/R target
            
            if tp > entry and entry > stop:
                return {
                    "strategy": StrategyName.BREAKOUT.value,
                    "symbol": symbol,
                    "direction": Direction.LONG.value,
                    "entry_price": entry,
                    "stop_loss": round(stop, 5),
                    "take_profit": round(tp, 5),
                    "reason": f"Bullish breakout: BB width={latest['bb_width']:.1f}% expanding, price={price:.5f} above upper band={latest['bb_upper']:.5f}, vol_ratio={latest['volume_ratio']:.2f}",
                    "indicators": {
                        "bb_width": latest['bb_width'],
                        "volume_ratio": latest['volume_ratio'],
                        "bb_upper": latest['bb_upper'],
                        "bb_mid": latest['bb_mid']
                    }
                }

        # ─── 2. Bearish Breakout (Sell) ───
        # Price crossed below lower Bollinger Band
        price_break_down = price <= latest['bb_lower'] or prev['close'] <= prev['bb_lower']
        
        if price_break_down:
            entry = price
            # SL inside the range, e.g. at the BB middle band or 1.5*ATR
            stop = max(latest['bb_mid'], price + (atr * 1.5))
            tp = price - (stop - price) * 2.5
            
            if tp < entry and entry < stop:
                return {
                    "strategy": StrategyName.BREAKOUT.value,
                    "symbol": symbol,
                    "direction": Direction.SHORT.value,
                    "entry_price": entry,
                    "stop_loss": round(stop, 5),
                    "take_profit": round(tp, 5),
                    "reason": f"Bearish breakout: BB width={latest['bb_width']:.1f}% expanding, price={price:.5f} below lower band={latest['bb_lower']:.5f}, vol_ratio={latest['volume_ratio']:.2f}",
                    "indicators": {
                        "bb_width": latest['bb_width'],
                        "volume_ratio": latest['volume_ratio'],
                        "bb_lower": latest['bb_lower'],
                        "bb_mid": latest['bb_mid']
                    }
                }

        return None


# Singleton
breakout_strategy = BreakoutStrategy()
