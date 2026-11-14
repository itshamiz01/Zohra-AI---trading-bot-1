"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — ANALYTICS & INTELLIGENCE                   ║
║         Gold Behavior, Market Condition, and Symbol Ranking          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any
from zohra.config.settings import DB_PATH
from zohra.brokers.manager import broker_manager as mt5_broker

logger = logging.getLogger("zohra.analytics")

# ─── 1. GOLD BEHAVIOR ENGINE ──────────────────────────────────────────
class GoldBehaviorEngine:
    """
    Dedicated intelligence for XAUUSD (Gold).
    Tracks session behavior: Asian accumulation, London sweeps, NY expansions, and COMEX volatility.
    """
    def analyze_gold_session(self) -> Dict[str, Any]:
        h = datetime.utcnow().hour
        symbol = "XAUUSD"
        
        # Default session characteristics
        session_type = "ASIAN_ACCUMULATION"
        volatility_profile = "LOW"
        bias = "NEUTRAL"
        thesis = "Gold is in the Asian session range accumulation phase."
        
        if 8 <= h < 12:
            session_type = "LONDON_MANIPULATION"
            volatility_profile = "MEDIUM_HIGH"
            thesis = "London open stop-hunts and liquidity sweeps are highly active."
        elif 12 <= h < 16:
            session_type = "NY_EXPANSION"
            volatility_profile = "HIGH"
            thesis = "New York expansion phase with peak institutional volume."
        elif 16 <= h < 21:
            session_type = "NY_LATE"
            volatility_profile = "MEDIUM"
            thesis = "Late New York session, profit-taking and consolidation."
            
        # Fetch recent M5 candles to calculate current volatility vs. average
        df = mt5_broker.get_ohlcv(symbol, "M5", count=40)
        if df is not None and len(df) >= 20:
            ranges = (df['high'] - df['low']).values
            current_range = ranges[-1]
            avg_range = ranges[-20:].mean()
            vol_ratio = current_range / (avg_range + 1e-9)
            
            if vol_ratio >= 1.8:
                volatility_profile = "EXCEPTIONAL_SPIKE"
                thesis += f" Volatility is spiking ({vol_ratio:.1f}x vs. 20-period SMA)."
            elif vol_ratio < 0.6:
                volatility_profile = "COMPRESSION"
                thesis += " Price is compressing into a tight range."

        return {
            "symbol": symbol,
            "session_type": session_type,
            "volatility_profile": volatility_profile,
            "bias": bias,
            "thesis": thesis,
            "timestamp": datetime.utcnow().isoformat()
        }


# ─── 2. MARKET CONDITION ENGINE ──────────────────────────────────────
class MarketConditionEngine:
    """
    Classifies general market states (Trending, Ranging, Expansion, Compression, Transition).
    """
    def classify_market(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df is None or len(df) < 30:
            return {"regime": "UNKNOWN", "volatility": "LOW", "strength": 0.0}

        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        
        # 1. Trend Strength (ADX)
        # Simple directional index calculation
        plus_dm = pd.Series(highs).diff().clip(lower=0)
        minus_dm = (-pd.Series(lows).diff()).clip(lower=0)
        tr = pd.concat([
            pd.Series(highs - lows),
            (pd.Series(highs) - pd.Series(closes).shift(1)).abs(),
            (pd.Series(lows) - pd.Series(closes).shift(1)).abs()
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / (atr + 1e-9)
        minus_di = 100 * minus_dm.rolling(14).mean() / (atr + 1e-9)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        adx = dx.rolling(14).mean().values[-1]
        
        # 2. Bollinger Band Width (Compression vs. Expansion)
        sma = pd.Series(closes).rolling(20).mean().values
        std = pd.Series(closes).rolling(20).std().values
        bb_width = (4 * std[-1]) / (sma[-1] + 1e-9) if len(std) > 0 else 0.0

        regime = "RANGING"
        if adx >= 25:
            regime = "TRENDING"
            if bb_width > 0.005:
                regime = "TRENDING_EXPANSION"
        else:
            if bb_width < 0.0015:
                regime = "COMPRESSION"
            elif bb_width > 0.004:
                regime = "RANGING_EXPANSION"

        return {
            "regime": regime,
            "adx_strength": float(adx),
            "bb_width": float(bb_width),
            "atr": float(atr.values[-1]) if len(atr) > 0 else 0.0,
            "timestamp": datetime.utcnow().isoformat()
        }


# ─── 3. SYMBOL RANKING ENGINE ────────────────────────────────────────
class SymbolRankingEngine:
    """
    Dynamically ranks symbols based on historical performance.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def rank_symbols(self) -> List[Dict[str, Any]]:
        """Queries database and ranks symbols by profit factor, win rate, and expectancy."""
        rankings = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Query closed trades grouped by symbol
                cursor.execute("""
                    SELECT 
                        symbol,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN pnl_usd <= 0 THEN 1 ELSE 0 END) as losses,
                        SUM(pnl_usd) as net_profit,
                        SUM(CASE WHEN pnl_usd > 0 THEN pnl_usd ELSE 0 END) as gross_profit,
                        SUM(CASE WHEN pnl_usd < 0 THEN ABS(pnl_usd) ELSE 0 END) as gross_loss
                    FROM trades
                    WHERE status = 'CLOSED'
                    GROUP BY symbol
                """)
                rows = cursor.fetchall()

                for r in rows:
                    total = r["total_trades"]
                    wins = r["wins"]
                    net = r["net_profit"]
                    gross_prof = r["gross_profit"]
                    gross_loss = r["gross_loss"]

                    win_rate = (wins / total * 100.0) if total > 0 else 0.0
                    profit_factor = (gross_prof / gross_loss) if gross_loss > 0 else (gross_prof if gross_prof > 0 else 1.0)
                    expectancy = (net / total) if total > 0 else 0.0

                    rankings.append({
                        "symbol": r["symbol"],
                        "total_trades": total,
                        "win_rate": win_rate,
                        "profit_factor": profit_factor,
                        "expectancy": expectancy,
                        "net_profit": net
                    })

                # Sort by net profit and expectancy
                rankings.sort(key=lambda x: (x["net_profit"], x["expectancy"]), reverse=True)
        except Exception as e:
            logger.error(f"Failed to rank symbols: {e}")

        # If no trade history, return default watchlist ranking
        if not rankings:
            return [
                {"symbol": "XAUUSD", "total_trades": 0, "win_rate": 0.0, "profit_factor": 1.0, "expectancy": 0.0, "net_profit": 0.0},
                {"symbol": "EURUSD", "total_trades": 0, "win_rate": 0.0, "profit_factor": 1.0, "expectancy": 0.0, "net_profit": 0.0},
                {"symbol": "GBPUSD", "total_trades": 0, "win_rate": 0.0, "profit_factor": 1.0, "expectancy": 0.0, "net_profit": 0.0},
                {"symbol": "USDJPY", "total_trades": 0, "win_rate": 0.0, "profit_factor": 1.0, "expectancy": 0.0, "net_profit": 0.0}
            ]

        return rankings

# Singletons
gold_behavior_engine = GoldBehaviorEngine()
market_condition_engine = MarketConditionEngine()
symbol_ranking_engine = SymbolRankingEngine()
