"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — ADAPTIVE SCORING ENGINE              ║
║  Confluence Engine + Dynamic Weights Scorer          ║
╚══════════════════════════════════════════════════════╝
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, List, Optional
from datetime import datetime

from zohra.core.enums import MarketRegime, Direction
from zohra.db.schema import db

logger = logging.getLogger("zohra.adaptive_scorer")


class AdaptiveScorer:
    """
    Evaluates 7 independent confluence modules (Layer 3) and 
    adjusts weights dynamically based on historical performance (Layer 4).
    """

    BASE_WEIGHTS = {
        "trending": {
            "structure": 25.0,
            "smc": 20.0,
            "volume": 15.0,
            "momentum": 15.0,
            "volatility": 10.0,
            "session": 10.0,
            "correlation": 5.0
        },
        "ranging": {
            "structure": 10.0,
            "smc": 25.0,
            "volume": 10.0,
            "momentum": 25.0,
            "volatility": 10.0,
            "session": 10.0,
            "correlation": 10.0
        },
        "breakout": {
            "structure": 15.0,
            "smc": 10.0,
            "volume": 25.0,
            "momentum": 20.0,
            "volatility": 15.0,
            "session": 10.0,
            "correlation": 5.0
        },
        "high_volatility": {
            "structure": 15.0,
            "smc": 15.0,
            "volume": 20.0,
            "momentum": 20.0,
            "volatility": 20.0,
            "session": 5.0,
            "correlation": 5.0
        },
        "low_liquidity": {
            "structure": 10.0,
            "smc": 10.0,
            "volume": 10.0,
            "momentum": 10.0,
            "volatility": 10.0,
            "session": 30.0,
            "correlation": 20.0
        },
        "news_driven": {
            "structure": 5.0,
            "smc": 5.0,
            "volume": 30.0,
            "momentum": 30.0,
            "volatility": 20.0,
            "session": 5.0,
            "correlation": 5.0
        }
    }

    # Mapping of logical modules to legacy trade database columns
    DB_MAPPINGS = {
        "structure": "score_structure",
        "smc": "score_smc",
        "volume": "score_liquidity",
        "momentum": "score_momentum",
        "volatility": "score_volatility",
        "session": "score_pullback",
        "correlation": "score_trend"
    }

    def __init__(self, min_history_count: int = 5):
        self.min_history_count = min_history_count

    # ════════════════════════════════════════════════
    #  LAYER 3: CONFLUENCE EVALUATIONS (0 - 100 EACH)
    # ════════════════════════════════════════════════

    def _find_pivots(self, data: np.ndarray, window: int = 5, high: bool = True) -> List[float]:
        pivots = []
        for i in range(window, len(data) - window):
            if high:
                if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] >= data[i+j] for j in range(1, window+1)):
                    pivots.append(float(data[i]))
            else:
                if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] <= data[i+j] for j in range(1, window+1)):
                    pivots.append(float(data[i]))
        return pivots[-8:]

    def _score_structure(self, df: pd.DataFrame, direction: str) -> Tuple[float, str]:
        """Module 1: Market Structure (HH/HL/LH/LL, BOS)"""
        if len(df) < 30:
            return 50.0, "Insufficient data"

        score = 0
        highs = df['high'].values
        lows  = df['low'].values
        
        recent_highs = self._find_pivots(highs, window=5, high=True)
        recent_lows  = self._find_pivots(lows,  window=5, high=False)
        
        if len(recent_highs) < 2 or len(recent_lows) < 2:
            return 50.0, "Structure unclear"

        reasons = []
        if direction == "LONG":
            if recent_highs[-1] > recent_highs[-2]:
                score += 40; reasons.append("HH formed")
            if recent_lows[-1] > recent_lows[-2]:
                score += 40; reasons.append("HL formed")
            if score >= 80:
                score += 20; reasons.append("Full bullish structure")
        else:
            if recent_highs[-1] < recent_highs[-2]:
                score += 40; reasons.append("LH formed")
            if recent_lows[-1] < recent_lows[-2]:
                score += 40; reasons.append("LL formed")
            if score >= 80:
                score += 20; reasons.append("Full bearish structure")

        score = max(10.0, float(min(score, 100)))
        return score, " | ".join(reasons) if reasons else "Structure neutral"

    def _score_smc(self, df: pd.DataFrame, direction: str) -> Tuple[float, str]:
        """Module 2: SMC Zones (Order Blocks, FVG, Premium/Discount)"""
        if len(df) < 30:
            return 50.0, "Insufficient data"

        score = 0
        reasons = []
        
        # Premium/Discount analysis (24-bar range)
        lookback = min(24, len(df) - 1)
        daily_high = df['high'].tail(lookback).max()
        daily_low  = df['low'].tail(lookback).min()
        daily_rng  = daily_high - daily_low
        
        if daily_rng <= 0:
            return 50.0, "Range zero"

        current = df.iloc[-1]['close']
        pct_range = (current - daily_low) / daily_rng

        if direction == "LONG":
            if pct_range <= 0.30:
                score += 60; reasons.append(f"Deep discount ({pct_range*100:.0f}%)")
            elif pct_range <= 0.50:
                score += 40; reasons.append(f"Discount zone ({pct_range*100:.0f}%)")
            else:
                score += 10; reasons.append(f"Premium zone ({pct_range*100:.0f}%)")
        else:
            if pct_range >= 0.70:
                score += 60; reasons.append(f"Deep premium ({pct_range*100:.0f}%)")
            elif pct_range >= 0.50:
                score += 40; reasons.append(f"Premium zone ({pct_range*100:.0f}%)")
            else:
                score += 10; reasons.append(f"Discount zone ({pct_range*100:.0f}%)")

        # OB check
        ob_found = False
        recent = df.tail(10)
        for i in range(len(recent) - 2):
            if direction == "LONG":
                if recent.iloc[i]['close'] < recent.iloc[i]['open'] and recent.iloc[i+1]['close'] > recent.iloc[i+1]['open'] and recent.iloc[i+1]['close'] > recent.iloc[i]['high']:
                    ob_found = True
            else:
                if recent.iloc[i]['close'] > recent.iloc[i]['open'] and recent.iloc[i+1]['close'] < recent.iloc[i+1]['open'] and recent.iloc[i+1]['close'] < recent.iloc[i]['low']:
                    ob_found = True
        
        if ob_found:
            score += 40; reasons.append("Order block present")
            
        score = max(10.0, float(min(score, 100)))
        return score, " | ".join(reasons) if reasons else "No clear zones"

    def _score_volume(self, df: pd.DataFrame) -> Tuple[float, str]:
        """Module 3: Volume (Tick volume vs rolling average)"""
        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'
        if vol_col not in df.columns or len(df) < 20:
            return 50.0, "No volume data"

        latest_vol = df[vol_col].iloc[-1]
        vol_sma = df[vol_col].rolling(20).mean().iloc[-1]
        
        ratio = latest_vol / (vol_sma + 1e-9)
        if ratio >= 1.5:
            return 100.0, f"Volume spike (x{ratio:.2f}) — strong confirmation"
        elif ratio >= 1.0:
            return 80.0, f"Average volume (x{ratio:.2f})"
        elif ratio >= 0.5:
            return 50.0, f"Below average volume (x{ratio:.2f})"
        else:
            return 20.0, f"Low liquidity volume (x{ratio:.2f}) — no confirmation"

    def _score_momentum(self, df: pd.DataFrame, direction: str) -> Tuple[float, str]:
        """Module 4: Momentum (RSI + MACD crossovers)"""
        if len(df) < 30:
            return 50.0, "Insufficient data"

        score = 50
        reasons = []
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = (100 - (100 / (1 + gain / (loss + 1e-9)))).iloc[-1]
        
        # MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        
        macd_val = macd.iloc[-1]
        signal_val = signal.iloc[-1]
        macd_prev = macd.iloc[-2]
        signal_prev = signal.iloc[-2]

        if direction == "LONG":
            if macd_val > signal_val:
                score += 20; reasons.append("MACD bullish")
            if macd_prev <= signal_prev and macd_val > signal_val:
                score += 15; reasons.append("MACD cross up")
            if 30 <= rsi <= 65:
                score += 15; reasons.append(f"RSI={rsi:.0f} constructive")
            elif rsi < 30:
                score += 10; reasons.append(f"RSI={rsi:.0f} oversold")
        else:
            if macd_val < signal_val:
                score += 20; reasons.append("MACD bearish")
            if macd_prev >= signal_prev and macd_val < signal_val:
                score += 15; reasons.append("MACD cross down")
            if 35 <= rsi <= 70:
                score += 15; reasons.append(f"RSI={rsi:.0f} constructive")
            elif rsi > 70:
                score += 10; reasons.append(f"RSI={rsi:.0f} overbought")

        score = max(10.0, float(min(score, 100)))
        return score, " | ".join(reasons)

    def _score_volatility(self, df: pd.DataFrame) -> Tuple[float, str]:
        """Module 5: Volatility (ATR sufficiency)"""
        if len(df) < 20:
            return 50.0, "Insufficient data"

        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1]
        price = df.iloc[-1]['close']
        vol_pct = (atr / price) * 100 if price > 0 else 0

        if vol_pct > 0.15:
            return 100.0, f"High volatility: ATR={atr:.5f} ({vol_pct:.3f}%)"
        elif vol_pct > 0.08:
            return 80.0, f"Moderate volatility: ATR={atr:.5f} ({vol_pct:.3f}%)"
        elif vol_pct > 0.04:
            return 50.0, f"Low volatility: ATR={atr:.5f} ({vol_pct:.3f}%)"
        else:
            return 20.0, f"Extremely low volatility: ATR={atr:.5f} ({vol_pct:.3f}%)"

    def _score_session(self) -> Tuple[float, str]:
        """Module 6: Session Timing (Overlap periods)"""
        h = datetime.utcnow().hour
        if 12 <= h < 16:
            return 100.0, "London-New York Overlap — Peak Liquidity"
        elif 8 <= h < 16:
            return 80.0, "London Session"
        elif 13 <= h < 21:
            return 80.0, "New York Session"
        elif 0 <= h < 8:
            return 45.0, "Asian Session — lower liquidity"
        else:
            return 15.0, "Off-hours / Illiquid gap"

    def _score_correlation(self, symbol: str) -> Tuple[float, str]:
        """Module 7: Correlation Check (Exposures mapping)"""
        try:
            open_trades = db.get_open_trades()
        except Exception as e:
            open_trades = []
            
        if not open_trades:
            return 100.0, "No open trades — correlation risk clear"

        # Groups of highly correlated assets
        correlation_groups = [
            {"EURUSD", "GBPUSD", "AUDUSD"},
            {"USDCAD", "USDJPY"}
        ]
        
        reasons = []
        multiplier = 1.0
        
        # Check matching symbols
        same_symbol_trades = [t for t in open_trades if t['symbol'] == symbol]
        if len(same_symbol_trades) >= 2:
            multiplier *= 0.3
            reasons.append(f"Multiple exposure: {len(same_symbol_trades)} positions already open in {symbol}")
        elif len(same_symbol_trades) == 1:
            multiplier *= 0.7
            reasons.append(f"Single exposure already open in {symbol}")

        # Check group correlation
        for group in correlation_groups:
            if symbol in group:
                group_trades = [t for t in open_trades if t['symbol'] in group and t['symbol'] != symbol]
                if group_trades:
                    multiplier *= 0.6
                    reasons.append(f"Correlated positions active: {[t['symbol'] for t in group_trades]}")

        final_score = float(max(10.0, 100.0 * multiplier))
        reason_str = " | ".join(reasons) if reasons else "No correlated risk active"
        return final_score, reason_str

    # ════════════════════════════════════════════════
    #  LAYER 4: ADAPTIVE SCORING & WEIGHTING SYNTHESIS
    # ════════════════════════════════════════════════

    def get_adaptive_weights(self, regime: MarketRegime, strategy: str) -> Dict[str, float]:
        """
        Query historical DB trades in current regime & strategy.
        Calculate Performance Factor (eta) for each module and adjust base weights.
        """
        regime_str = regime.value if isinstance(regime, MarketRegime) else str(regime)
        
        # Base weights fallback
        base = dict(self.BASE_WEIGHTS.get(regime_str, self.BASE_WEIGHTS['ranging']))
        
        try:
            # Look up the last 30 closed trades in this regime and strategy
            trades = db._execute("""
                SELECT pnl_usd, score_structure, score_liquidity, score_smc, score_trend, score_momentum, score_volatility, score_pullback
                FROM trades
                WHERE timestamp_close IS NOT NULL AND market_regime = ? AND strategy_used = ?
                ORDER BY timestamp_close DESC LIMIT 30
            """, (regime_str, strategy), fetch="all")
        except Exception as e:
            logger.warning(f"Failed to query trade history for adaptive weights: {e}")
            trades = []

        if not trades or len(trades) < self.min_history_count:
            return base

        adjusted = {}
        for module, db_col in self.DB_MAPPINGS.items():
            # Filter trades where the module supported the decision (score >= 50)
            module_trades = [t for t in trades if (t.get(db_col) or 0) >= 50]
            
            if len(module_trades) < self.min_history_count:
                adjusted[module] = base[module]
                continue

            wins = sum(1 for t in module_trades if (t.get('pnl_usd') or 0.0) > 0.0)
            wr = wins / len(module_trades)

            gross_profit = sum(t.get('pnl_usd') or 0.0 for t in module_trades if (t.get('pnl_usd') or 0.0) > 0.0)
            gross_loss = sum(abs(t.get('pnl_usd') or 0.0) for t in module_trades if (t.get('pnl_usd') or 0.0) < 0.0)
            pf = gross_profit / gross_loss if gross_loss > 0 else 2.0

            # Performance Factor (eta) Formula
            eta = 0.6 * wr + 0.4 * min(2.0, pf / 1.5)
            
            # Bound dynamic multiplier to [0.2, 2.0]
            eta = max(0.2, min(2.0, eta))
            
            adjusted[module] = round(base[module] * eta, 2)
            logger.debug(f"Module {module} eta={eta:.2f} | Base weight={base[module]} -> Adjusted={adjusted[module]}")

        return adjusted

    def evaluate_confluence(self, df: pd.DataFrame, direction: str, symbol: str,
                            regime: MarketRegime, strategy: str) -> dict:
        """
        Synthesizes the final score using confluence module calculations and
        dynamically adjusted weights.
        """
        # 1. Compute scores
        s_struct, r_struct = self._score_structure(df, direction)
        s_smc, r_smc       = self._score_smc(df, direction)
        s_vol, r_vol       = self._score_volume(df)
        s_mom, r_mom       = self._score_momentum(df, direction)
        s_vlt, r_vlt       = self._score_volatility(df)
        s_sess, r_sess     = self._score_session()
        s_corr, r_corr     = self._score_correlation(symbol)

        scores = {
            "structure": s_struct,
            "smc": s_smc,
            "volume": s_vol,
            "momentum": s_mom,
            "volatility": s_vlt,
            "session": s_sess,
            "correlation": s_corr
        }

        reasons = {
            "structure": r_struct,
            "smc": r_smc,
            "volume": r_vol,
            "momentum": r_mom,
            "volatility": r_vlt,
            "session": r_sess,
            "correlation": r_corr
        }

        # 2. Get adaptive weights
        weights = self.get_adaptive_weights(regime, strategy)

        # 3. Calculate weighted average
        weighted_sum = sum(scores[k] * weights[k] for k in scores)
        total_weight = sum(weights.values())
        
        final_score = weighted_sum / (total_weight + 1e-9)
        final_score = int(round(final_score))

        return {
            "final_score": final_score,
            "scores": scores,
            "weights": weights,
            "reasons": reasons
        }


# Singleton
adaptive_scorer = AdaptiveScorer()
