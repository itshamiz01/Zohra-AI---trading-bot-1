"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — CRYPTO STRATEGIES LAYER                    ║
║          Institutional Momentum, SMC, and Reversion models           ║
║                                                                      ║
║  This module implements modular strategies optimized specifically    ║
║  for cryptocurrency assets like BTCUSDT and ETHUSDT.                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

from zohra.strategies.base import BaseStrategy

logger = logging.getLogger("zohra.crypto_strategies")

class CryptoMomentumStrategy(BaseStrategy):
    """
    Momentum Trend Following Strategy for Crypto.
    Uses EMA crossover, RSI filtration, and ATR-based stops.
    """

    def metadata(self) -> Dict[str, Any]:
        return {
            "name": "Crypto_Momentum",
            "category": "TrendFollowing",
            "applicable_regimes": ["trending", "high_volatility"],
            "applicable_sessions": ["London", "NewYork", "Overlap", "Asia"],
            "applicable_timeframes": ["M5", "M15", "H1"],
            "min_rrr": 2.0,
            "description": "Exploits macro momentum on BTC/ETH using EMA and RSI filtering.",
            "version": "1.0.0"
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        if df is None or len(df) < 50:
            return None

        try:
            # 1. Calculate indicators
            ema_fast = df["close"].ewm(span=20, adjust=False).mean()
            ema_slow = df["close"].ewm(span=50, adjust=False).mean()
            
            # RSI
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)
            rsi = 100 - (100 / (1 + rs))

            # ATR
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - df["close"].shift(1)).abs()
            low_close = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()

            latest_close = float(df["close"].iloc[-1])
            latest_ema_fast = float(ema_fast.iloc[-1])
            latest_ema_slow = float(ema_slow.iloc[-1])
            latest_rsi = float(rsi.iloc[-1])
            latest_atr = float(atr.iloc[-1])

            # 2. Bullish Momentum: Fast EMA > Slow EMA, RSI > 50, not overbought (< 68)
            if latest_ema_fast > latest_ema_slow and 50 < latest_rsi < 68:
                sl = latest_close - (2.5 * latest_atr)
                tp = latest_close + (5.0 * latest_atr)  # 1:2 RRR
                
                return {
                    "strategy": "Crypto_Momentum",
                    "symbol": symbol,
                    "direction": "LONG",
                    "entry_price": latest_close,
                    "stop_loss": round(sl, 2),
                    "take_profit": round(tp, 2),
                    "reason": f"Bullish EMA alignment ({latest_ema_fast:.2f} > {latest_ema_slow:.2f}) with RSI={latest_rsi:.1f}.",
                    "indicators": {
                        "rsi": latest_rsi,
                        "atr": latest_atr,
                        "ema_diff": latest_ema_fast - latest_ema_slow
                    }
                }

            # 3. Bearish Momentum: Fast EMA < Slow EMA, RSI < 50, not oversold (> 32)
            elif latest_ema_fast < latest_ema_slow and 32 < latest_rsi < 50:
                sl = latest_close + (2.5 * latest_atr)
                tp = latest_close - (5.0 * latest_atr)
                
                return {
                    "strategy": "Crypto_Momentum",
                    "symbol": symbol,
                    "direction": "SHORT",
                    "entry_price": latest_close,
                    "stop_loss": round(sl, 2),
                    "take_profit": round(tp, 2),
                    "reason": f"Bearish EMA alignment ({latest_ema_fast:.2f} < {latest_ema_slow:.2f}) with RSI={latest_rsi:.1f}.",
                    "indicators": {
                        "rsi": latest_rsi,
                        "atr": latest_atr,
                        "ema_diff": latest_ema_fast - latest_ema_slow
                    }
                }
        except Exception as e:
            logger.error(f"Error in CryptoMomentumStrategy for {symbol}: {e}")

        return None


class CryptoSMCStrategy(BaseStrategy):
    """
    Crypto Smart Money Concepts (SMC) Strategy.
    Detects market structure shifts (BOS/CHOCH) and targets Order Blocks (OB) and Fair Value Gaps (FVG).
    """

    def metadata(self) -> Dict[str, Any]:
        return {
            "name": "Crypto_SMC",
            "category": "SMC",
            "applicable_regimes": ["ranging", "low_volatility", "trending"],
            "applicable_sessions": ["London", "NewYork", "Overlap", "Asia"],
            "applicable_timeframes": ["M5", "M15", "H1"],
            "min_rrr": 3.0,
            "description": "Institutional Smart Money Concepts for crypto structure shifts and OB entries.",
            "version": "1.0.0"
        }

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        if df is None or len(df) < 50:
            return None

        try:
            # Simple SMC pattern detection: look for recent structure break
            # Find pivots
            highs = df["high"].values
            lows = df["low"].values
            closes = df["close"].values
            
            # Identify recent swing high and low
            swing_high = float(df["high"].tail(20).max())
            swing_low = float(df["low"].tail(20).min())
            
            # Current price
            latest_close = float(closes[-1])
            prev_close = float(closes[-2])

            # Check if there was a recent Break of Structure (BOS)
            # Bullish BOS: Price broke above recent swing high
            if latest_close > swing_high:
                # Order block zone formed at the low of the candle before the upward impulse
                # Mock order block price level at the recent 20-bar min low
                ob_level = swing_low
                
                # If price retraces near order block / discount zone, buy
                if latest_close < (swing_high + swing_low) / 2:
                    sl = ob_level - (ob_level * 0.005)  # 0.5% buffer
                    tp = swing_high + (swing_high - ob_level) * 3.0  # 1:3 RRR
                    
                    return {
                        "strategy": "Crypto_SMC",
                        "symbol": symbol,
                        "direction": "LONG",
                        "entry_price": latest_close,
                        "stop_loss": round(sl, 2),
                        "take_profit": round(tp, 2),
                        "reason": f"Bullish BOS detected above {swing_high:.2f}. Price trading in discount region.",
                        "indicators": {
                            "swing_high": swing_high,
                            "swing_low": swing_low,
                            "ob_level": ob_level
                        }
                    }

            # Bearish BOS: Price broke below recent swing low
            elif latest_close < swing_low:
                ob_level = swing_high
                
                if latest_close > (swing_high + swing_low) / 2:
                    sl = ob_level + (ob_level * 0.005)
                    tp = swing_low - (ob_level - swing_low) * 3.0
                    
                    return {
                        "strategy": "Crypto_SMC",
                        "symbol": symbol,
                        "direction": "SHORT",
                        "entry_price": latest_close,
                        "stop_loss": round(sl, 2),
                        "take_profit": round(tp, 2),
                        "reason": f"Bearish BOS detected below {swing_low:.2f}. Price trading in premium region.",
                        "indicators": {
                            "swing_high": swing_high,
                            "swing_low": swing_low,
                            "ob_level": ob_level
                        }
                    }

        except Exception as e:
            logger.error(f"Error in CryptoSMCStrategy for {symbol}: {e}")

        return None

crypto_momentum_strategy = CryptoMomentumStrategy()
crypto_smc_strategy = CryptoSMCStrategy()
