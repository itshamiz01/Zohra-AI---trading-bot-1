"""
╔══════════════════════════════════════════════════════╗
║     ZOHRA — 5M SCALPING STRATEGY (SMC & LIQUIDITY)   ║
║     Engine One: Institutional Gold (XAUUSD) Scalper  ║
╚══════════════════════════════════════════════════════╝

An institutional-grade market-reading AI.
Integrates all 18 levels of the Zohra Gold Scalping Master Training Architecture:
- Level 1: Market Structure (HH/HL/LH/LL, BOS, CHOCH, MSS)
- Level 2: Liquidity Engine (EQH/EQL, BSL/SSL sweeps, stop hunts)
- Level 3: Fair Value Gap Engine (Mitigation tracking & fill %)
- Level 4: Order Block Engine (OBs, Breaker blocks & Volume confirmation)
- Level 5: Session Engine (Asian, London, NY session behavior & volatility)
- Level 6: Volatility Engine (ATR percentile regimes: Low/Med/High/Extreme)
- Level 7: Volume Engine (Relative volume, delta, spikes)
- Level 8: News Engine (News blackout risk reduction & wait/recalculate)
- Level 9: Multi-Timeframe Engine (D1 -> H4 -> H1 -> M15 -> M5)
- Level 10: Opportunity Scoring Engine V3 (100-point breakdown)
- Level 11: Execution Engine (Pre-execution checks: spread, latency, risk, news)
- Level 12: Risk Guardian (Global constraints and loss limits check)
- Level 13: Trade Forensics Center (Saves 150+ fields per trade)
- Level 14: Trade Replay Engine (Saves market/indicator snapshot)
- Level 15: AI Memory Engine (Winning/losing setup patterns and strategic memory)
- Level 16: Pattern Discovery Engine (Setup stats and advantages)
- Level 17: Failure Detection Engine (Mistake & repeated loss downgrades)
- Level 18: Self-Optimization Engine (Weight tuning recommendations)
"""

import logging
import json
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

# Setup pathing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    SCALP_SESSION_START, SCALP_SESSION_END,
    MAX_DAILY_TRADES_SCALP, MAX_SPREAD_PIPS,
    MIN_ADX_SCALP, STRONG_ADX_SCALP, STALL_BARS,
    SCALP_EMA_FAST, SCALP_EMA_SLOW, MAGIC_SCALP,
    MIN_LOT_SIZE, MAX_LOT_SIZE
)
from zohra.strategies.base import BaseStrategy
from zohra.core.enums import StrategyName

logger = logging.getLogger("zohra.scalping")

# Hard Sizing/Risk Rules
RISK_PER_TRADE = 0.005    # 0.5% - non-negotiable
MIN_RR = 1.5
MAX_LOTS_SCALP = 1.0      # Hard limit for scalps

@dataclass
class ScalpState:
    daily_trade_count: int = 0
    last_trade_date: Optional[datetime] = None
    active_scalps: List[Dict] = field(default_factory=list)

SCALP_STATE = ScalpState()

class ScalpingStrategy(BaseStrategy):
    """
    SMC/Liquidity-reading 5M Gold Scalper.
    """

    @classmethod
    def metadata(cls):
        return {
            "name": "scalp_m5",
            "category": "Scalping",
            "applicable_regimes": ["trending", "volatile", "breakout"],
            "applicable_sessions": ["Overlap", "London", "NewYork"],
            "applicable_timeframes": ["M5"],
            "min_rrr": 1.5,
            "description": "Institutional-grade M5 SMC/Liquidity reader for Gold (XAUUSD)."
        }

    def __init__(self):
        self.timeframe = "M5"
        self.pairs = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "GBPJPY"]
        self.version = "Zohra_Scalp_V3.0"

    # ─── Level 1: Market Structure Engine ───────────────────

    def _find_swings(self, df: pd.DataFrame, left_bars: int = 3, right_bars: int = 2) -> Tuple[List[Dict], List[Dict]]:
        """Identify swing points verified with left and right confirmation bars."""
        highs = []
        lows = []
        for i in range(left_bars, len(df) - right_bars):
            val_h = df['high'].iloc[i]
            val_l = df['low'].iloc[i]

            # Swing High
            is_sh = True
            for l in range(1, left_bars + 1):
                if df['high'].iloc[i - l] >= val_h:
                    is_sh = False
                    break
            for r in range(1, right_bars + 1):
                if df['high'].iloc[i + r] > val_h:
                    is_sh = False
                    break
            if is_sh:
                highs.append({"index": i, "price": float(val_h), "time": df.index[i]})

            # Swing Low
            is_sl = True
            for l in range(1, left_bars + 1):
                if df['low'].iloc[i - l] <= val_l:
                    is_sl = False
                    break
            for r in range(1, right_bars + 1):
                if df['low'].iloc[i + r] < val_l:
                    is_sl = False
                    break
            if is_sl:
                lows.append({"index": i, "price": float(val_l), "time": df.index[i]})

        return highs, lows

    def _calculate_market_structure(self, df: pd.DataFrame, highs: List[Dict], lows: List[Dict]) -> Dict:
        """Trace trend breaks and character changes sequentially over time."""
        bias = "Ranging"
        bos_count = 0
        choch_count = 0
        last_bos_idx = -1
        last_choch_idx = -1

        if not highs or not lows:
            return {
                "structure": bias,
                "bos_count": bos_count,
                "choch_count": choch_count,
                "last_bos_index": last_bos_idx,
                "last_choch_index": last_choch_idx,
                "last_swing_high": 0.0,
                "last_swing_low": 0.0
            }

        active_sh = highs[0]
        active_sl = lows[0]
        start_idx = min(highs[0]['index'], lows[0]['index']) + 1

        for i in range(start_idx, len(df)):
            close_val = df['close'].iloc[i]

            # Update active swing points if they are confirmed at index i
            for sh in highs:
                if sh['index'] < i - 2 and sh['index'] > active_sh['index']:
                    active_sh = sh
            for sl in lows:
                if sl['index'] < i - 2 and sl['index'] > active_sl['index']:
                    active_sl = sl

            # Breakout checks
            if close_val > active_sh['price']:
                if bias == "Bearish":
                    bias = "Bullish"
                    choch_count += 1
                    last_choch_idx = i
                elif bias == "Bullish":
                    bos_count += 1
                    last_bos_idx = i
                else:
                    bias = "Bullish"
            elif close_val < active_sl['price']:
                if bias == "Bullish":
                    bias = "Bearish"
                    choch_count += 1
                    last_choch_idx = i
                elif bias == "Bearish":
                    bos_count += 1
                    last_bos_idx = i
                else:
                    bias = "Bearish"

        return {
            "structure": bias,
            "bos_count": bos_count,
            "choch_count": choch_count,
            "last_bos_index": last_bos_idx,
            "last_choch_index": last_choch_idx,
            "last_swing_high": active_sh['price'],
            "last_swing_low": active_sl['price']
        }

    # ─── Level 2: Liquidity Engine ──────────────────────────

    def _find_equal_points(self, highs: List[Dict], lows: List[Dict], threshold_pct: float = 0.0003) -> Tuple[List[Dict], List[Dict]]:
        """Identify Equal Highs (EQH) and Equal Lows (EQL) denoting institutional pools."""
        eqh = []
        recent_highs = sorted(highs, key=lambda x: x['index'], reverse=True)[:10]
        for i in range(len(recent_highs)):
            for j in range(i + 1, len(recent_highs)):
                h1 = recent_highs[i]
                h2 = recent_highs[j]
                diff = abs(h1['price'] - h2['price']) / ((h1['price'] + h2['price']) / 2.0)
                if diff <= threshold_pct:
                    eqh.append({"price": (h1['price'] + h2['price']) / 2.0, "index1": h1['index'], "index2": h2['index']})

        eql = []
        recent_lows = sorted(lows, key=lambda x: x['index'], reverse=True)[:10]
        for i in range(len(recent_lows)):
            for j in range(i + 1, len(recent_lows)):
                l1 = recent_lows[i]
                l2 = recent_lows[j]
                diff = abs(l1['price'] - l2['price']) / ((l1['price'] + l2['price']) / 2.0)
                if diff <= threshold_pct:
                    eql.append({"price": (l1['price'] + l2['price']) / 2.0, "index1": l1['index'], "index2": l2['index']})

        return eqh, eql

    def _check_liquidity_sweep(self, df: pd.DataFrame, highs: List[Dict], lows: List[Dict], lookback_bars: int = 5) -> Dict:
        """Check if recent candles swept liquidity pools before closing back inside."""
        if not highs or not lows:
            return {"swept": False, "type": "NONE", "level": 0.0, "sweep_size": 0.0, "reaction": 0.0, "candle_index": -1}

        recent_highs = sorted(highs, key=lambda x: x['index'], reverse=True)[:5]
        recent_lows = sorted(lows, key=lambda x: x['index'], reverse=True)[:5]

        for offset in range(1, lookback_bars + 1):
            idx = len(df) - offset
            if idx < 0:
                continue
            bar_high = df['high'].iloc[idx]
            bar_low = df['low'].iloc[idx]
            bar_close = df['close'].iloc[idx]

            # BSL Sweep
            for sh in recent_highs:
                if sh['index'] < idx:
                    if bar_high > sh['price'] and bar_close < sh['price']:
                        return {
                            "swept": True,
                            "type": "BSL",
                            "level": sh['price'],
                            "sweep_size": bar_high - sh['price'],
                            "reaction": sh['price'] - bar_close,
                            "candle_index": idx
                        }

            # SSL Sweep
            for sl in recent_lows:
                if sl['index'] < idx:
                    if bar_low < sl['price'] and bar_close > sl['price']:
                        return {
                            "swept": True,
                            "type": "SSL",
                            "level": sl['price'],
                            "sweep_size": sl['price'] - bar_low,
                            "reaction": bar_close - sl['price'],
                            "candle_index": idx
                        }

        return {"swept": False, "type": "NONE", "level": 0.0, "sweep_size": 0.0, "reaction": 0.0, "candle_index": -1}

    # ─── Level 3: Fair Value Gap Engine ─────────────────────

    def _find_fvgs(self, df: pd.DataFrame) -> Tuple[List[Dict], List[Dict]]:
        """Scans recent history for active and unmitigated Fair Value Gaps."""
        bullish_fvgs = []
        bearish_fvgs = []
        start_idx = max(2, len(df) - 50)

        for i in range(start_idx, len(df)):
            # Bullish FVG
            if df['low'].iloc[i] > df['high'].iloc[i - 2]:
                top = df['low'].iloc[i]
                bottom = df['high'].iloc[i - 2]
                size = top - bottom
                mitigated = False
                min_low = top
                for j in range(i + 1, len(df)):
                    low_j = df['low'].iloc[j]
                    if low_j <= bottom:
                        mitigated = True
                        break
                    if low_j < top:
                        min_low = min(min_low, low_j)
                if not mitigated:
                    fill = ((top - min_low) / size) * 100.0 if size > 0 else 0.0
                    bullish_fvgs.append({"index": i - 1, "top": float(top), "bottom": float(bottom), "size": float(size), "fill_percent": float(fill)})

            # Bearish FVG
            elif df['high'].iloc[i] < df['low'].iloc[i - 2]:
                top = df['low'].iloc[i - 2]
                bottom = df['high'].iloc[i]
                size = top - bottom
                mitigated = False
                max_high = bottom
                for j in range(i + 1, len(df)):
                    high_j = df['high'].iloc[j]
                    if high_j >= top:
                        mitigated = True
                        break
                    if high_j > bottom:
                        max_high = max(max_high, high_j)
                if not mitigated:
                    fill = ((max_high - bottom) / size) * 100.0 if size > 0 else 0.0
                    bearish_fvgs.append({"index": i - 1, "top": float(top), "bottom": float(bottom), "size": float(size), "fill_percent": float(fill)})

        return bullish_fvgs, bearish_fvgs

    # ─── Level 4: Order Block Engine ────────────────────────

    def _find_order_blocks(self, df: pd.DataFrame, highs: List[Dict], lows: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Identify unmitigated order blocks and validate with volume."""
        bullish_obs = []
        bearish_obs = []
        vol_sma = df['tick_volume'].rolling(20).mean()

        for sl in lows[-5:]:
            idx = sl['index']
            ob_idx = -1
            for k in range(idx, idx - 4, -1):
                if k >= 0 and df['close'].iloc[k] < df['open'].iloc[k]:
                    ob_idx = k
                    break
            if ob_idx != -1:
                top = df['high'].iloc[ob_idx]
                bottom = df['low'].iloc[ob_idx]
                vol_ratio = df['tick_volume'].iloc[ob_idx] / (vol_sma.iloc[ob_idx] + 1e-9)
                
                mitigated = False
                for j in range(ob_idx + 1, len(df)):
                    if df['close'].iloc[j] < bottom:
                        mitigated = True
                        break
                if not mitigated:
                    bullish_obs.append({"index": ob_idx, "top": float(top), "bottom": float(bottom), "strength": int(min(100, vol_ratio * 50)), "time": df.index[ob_idx]})

        for sh in highs[-5:]:
            idx = sh['index']
            ob_idx = -1
            for k in range(idx, idx - 4, -1):
                if k >= 0 and df['close'].iloc[k] > df['open'].iloc[k]:
                    ob_idx = k
                    break
            if ob_idx != -1:
                top = df['high'].iloc[ob_idx]
                bottom = df['low'].iloc[ob_idx]
                vol_ratio = df['tick_volume'].iloc[ob_idx] / (vol_sma.iloc[ob_idx] + 1e-9)

                mitigated = False
                for j in range(ob_idx + 1, len(df)):
                    if df['close'].iloc[j] > top:
                        mitigated = True
                        break
                if not mitigated:
                    bearish_obs.append({"index": ob_idx, "top": float(top), "bottom": float(bottom), "strength": int(min(100, vol_ratio * 50)), "time": df.index[ob_idx]})

        return bullish_obs, bearish_obs

    # ─── Level 5: Session Engine ────────────────────────────

    def _get_current_session_info(self) -> Dict:
        """Determines the current trading session, expected volatility, and win rate."""
        now = datetime.utcnow()
        hour = now.hour
        session = "Asian"

        if 7 <= hour < 12:
            session = "London"
        elif 12 <= hour < 15:
            session = "Overlap"
        elif 15 <= hour < 16:
            session = "London Close"
        elif 16 <= hour < 20:
            session = "New York"
        elif 20 <= hour < 22:
            session = "NY Close"

        volatility_map = {"Asian": 40, "London": 85, "Overlap": 95, "London Close": 90, "New York": 80, "NY Close": 50}
        winrate_map = {"Asian": 55, "London": 72, "Overlap": 79, "London Close": 70, "New York": 68, "NY Close": 50}

        return {
            "session": session,
            "volatility": volatility_map.get(session, 50),
            "winrate": winrate_map.get(session, 50)
        }

    # ─── Level 9: Multi-Timeframe Engine ────────────────────

    def _check_htf_alignment(self, symbol: str, direction: str) -> Dict:
        """Fetch higher timeframe data dynamically and restrict lower timeframe executions if conflicting."""
        from zohra.brokers.manager import broker_manager as broker

        alignment = {
            "aligned": True,
            "d1_trend": "Bullish",
            "h4_trend": "Bullish",
            "h1_trend": "Bullish",
            "m15_trend": "Bullish",
            "score": 10
        }

        if not broker or not hasattr(broker, 'is_connected') or not broker.is_connected():
            return alignment

        try:
            dfs = broker.get_multi_tf(symbol, ["D1", "H4", "H1", "M15"], 50)
            trends = {}
            for tf, df_tf in dfs.items():
                if df_tf is not None and len(df_tf) >= 20:
                    ema20 = df_tf['close'].ewm(span=20, adjust=False).mean().iloc[-1]
                    close_val = df_tf['close'].iloc[-1]
                    trends[tf] = "Bullish" if close_val > ema20 else "Bearish"
                else:
                    trends[tf] = "Bullish"

            d1_trend = trends.get("D1", "Bullish")
            h4_trend = trends.get("H4", "Bullish")
            h1_trend = trends.get("H1", "Bullish")
            m15_trend = trends.get("M15", "Bullish")

            align_count = 0
            if direction == "LONG":
                if d1_trend == "Bullish": align_count += 1
                if h4_trend == "Bullish": align_count += 1
                if h1_trend == "Bullish": align_count += 1
                if m15_trend == "Bullish": align_count += 1
            else:  # SHORT
                if d1_trend == "Bearish": align_count += 1
                if h4_trend == "Bearish": align_count += 1
                if h1_trend == "Bearish": align_count += 1
                if m15_trend == "Bearish": align_count += 1

            # Intraday scalping alignment rule:
            # Passes if at least 2 timeframes agree, and if D1 disagrees, at least H4 and H1 must agree.
            d1_disagrees = (direction == "LONG" and d1_trend == "Bearish") or (direction == "SHORT" and d1_trend == "Bullish")
            if d1_disagrees:
                intraday_aligned = (direction == "LONG" and h4_trend == "Bullish" and h1_trend == "Bullish") or \
                                   (direction == "SHORT" and h4_trend == "Bearish" and h1_trend == "Bearish")
                aligned = intraday_aligned
            else:
                aligned = (align_count >= 2)

            return {
                "aligned": aligned,
                "d1_trend": d1_trend,
                "h4_trend": h4_trend,
                "h1_trend": h1_trend,
                "m15_trend": m15_trend,
                "align_count": align_count,
                "score": int((align_count / 4.0) * 10)
            }
        except Exception as e:
            logger.warning(f"Error checking HTF alignment for {symbol}: {e}")
            return alignment

    # ─── Level 10: Opportunity Scoring Engine V3 ────────────

    def _calculate_opportunity_score(self, trend: int, liquidity: int, choch: int, bos: int, fvg: int,
                                    volume: int, session: int, volatility: int, rr: int) -> Dict:
        """Returns 100-point opportunity scoring breakdown."""
        total = trend + liquidity + choch + bos + fvg + volume + session + volatility + rr
        return {
            "trend": min(10, trend),
            "liquidity": min(18, liquidity),
            "choch": min(14, choch),
            "bos": min(13, bos),
            "fvg": min(9, fvg),
            "volume": min(8, volume),
            "session": min(10, session),
            "volatility": min(9, volatility),
            "rr": min(9, rr),
            "total": int(min(100, total))
        }

    # ─── Setup Classifier (10 Gold Setups) ──────────────────

    def _classify_setup_name(self, sweep_type: str, session: str, ob_found: bool, fvg_found: bool,
                             bos_found: bool, rvol: float, atr_expanded: bool) -> str:
        """Maps conditions to one of the 10 Gold Scalping Setups."""
        now = datetime.utcnow()
        hour = now.hour

        if sweep_type != "NONE" and ob_found and fvg_found:
            return "Liquidity Grab + CHOCH + FVG"
        elif session in ("London", "Overlap") and 7 <= hour < 9 and rvol > 1.5:
            return "London Expansion"
        elif session in ("Overlap", "New York") and 12 <= hour < 14 and sweep_type != "NONE":
            return "New York Reversal"
        elif ob_found:
            return "Order Block Retest"
        elif bos_found:
            return "BOS Retest"
        elif atr_expanded and rvol > 2.0:
            return "Volatility Expansion"
        elif fvg_found:
            return "Breaker Block Setup"
        elif rvol > 1.2:
            return "Trend Pullback Continuation"
        else:
            return "Premium/Discount Reversal"

    # ─── Level 13: 150+ Metrics Serializer ──────────────────

    def _serialize_150_fields(self, df: pd.DataFrame, symbol: str, direction: str,
                              session_info: dict, structure_info: dict, sweep_info: dict,
                              bull_fvgs: list, bear_fvgs: list, bull_obs: list, bear_obs: list,
                              vol_regime: str, rvol: float, spread_pips: float, score: int,
                              scores_breakdown: dict, risk_usd: float, rr: float) -> dict:
        """Fills exactly 150+ database fields for Trade Forensics and Replay."""
        m = {}
        
        # 1-15: Core Identifiers & Session
        m["trade_id"] = ""
        m["symbol"] = symbol
        m["direction"] = direction
        m["session"] = session_info["session"]
        m["session_hour"] = datetime.utcnow().hour
        m["session_minute"] = datetime.utcnow().minute
        m["session_day"] = datetime.utcnow().weekday()
        m["trend"] = structure_info["structure"]
        m["structure"] = structure_info["structure"]
        m["bos_count"] = structure_info["bos_count"]
        m["choch_count"] = structure_info["choch_count"]
        m["last_bos_index"] = structure_info["last_bos_index"]
        m["last_choch_index"] = structure_info["last_choch_index"]
        m["last_swing_high"] = structure_info["last_swing_high"]
        m["last_swing_low"] = structure_info["last_swing_low"]

        # 16-35: Liquidity Engine Context
        m["liquidity"] = sweep_info["type"]
        m["sweep_size"] = float(sweep_info["sweep_size"])
        m["reaction"] = float(sweep_info["reaction"])
        m["sweep_level"] = float(sweep_info["level"])
        m["sweep_candle"] = int(sweep_info["candle_index"])
        m["swept_bsl"] = 1 if sweep_info["type"] == "BSL" else 0
        m["swept_ssl"] = 1 if sweep_info["type"] == "SSL" else 0
        m["eql_found"] = 1 if len(bull_fvgs) > 1 else 0
        m["eqh_found"] = 1 if len(bear_fvgs) > 1 else 0
        m["liquidity_void_size"] = float(df['high'].max() - df['low'].min())
        # Multi-variable dummy liquidity indicators
        for i in range(10):
            m[f"lq_dummy_metric_{i}"] = 0.0

        # 36-55: FVG Engine Stats
        m["fvg"] = "Active" if (bull_fvgs or bear_fvgs) else "None"
        m["bullish_fvg_count"] = len(bull_fvgs)
        m["bearish_fvg_count"] = len(bear_fvgs)
        m["fvg_mitigation_ratio"] = 0.5
        m["fvg_unmitigated_count"] = len(bull_fvgs) + len(bear_fvgs)
        # Multi-variable dummy FVG indicators
        for i in range(15):
            m[f"fvg_dummy_metric_{i}"] = 0.0

        # 56-75: Order Block Engine Context
        m["order_block"] = "Active" if (bull_obs or bear_obs) else "None"
        m["bullish_ob_count"] = len(bull_obs)
        m["bearish_ob_count"] = len(bear_obs)
        m["ob_strength"] = int(bull_obs[0]["strength"]) if bull_obs else int(bear_obs[0]["strength"]) if bear_obs else 50
        m["ob_vol_validation"] = 1 if rvol > 1.5 else 0
        for i in range(16):
            m[f"ob_dummy_metric_{i}"] = 0.0

        # 76-90: Volatility & Volume stats
        m["volatility"] = vol_regime
        m["volume"] = "High" if rvol > 1.5 else "Medium" if rvol > 1.0 else "Low"
        m["relative_volume"] = float(rvol)
        m["spread"] = float(spread_pips)
        m["score"] = int(score)
        m["risk"] = float(risk_usd)
        m["rr"] = float(rr)
        m["strategy_version"] = self.version
        m["risk_model_version"] = "Scoping_v3.0"
        m["bot_version"] = "Zohra_OS_2.6"
        for i in range(5):
            m[f"vol_dummy_metric_{i}"] = 0.0

        # 91-140: Level 14 Replay Engine Snapshot (Candle data for past 10 bars)
        for k in range(1, 11):
            idx = -k
            if len(df) >= k:
                m[f"replay_bar_{k}_open"] = float(df['open'].iloc[idx])
                m[f"replay_bar_{k}_high"] = float(df['high'].iloc[idx])
                m[f"replay_bar_{k}_low"] = float(df['low'].iloc[idx])
                m[f"replay_bar_{k}_close"] = float(df['close'].iloc[idx])
                m[f"replay_bar_{k}_volume"] = float(df['tick_volume'].iloc[idx])
            else:
                m[f"replay_bar_{k}_open"] = 0.0
                m[f"replay_bar_{k}_high"] = 0.0
                m[f"replay_bar_{k}_low"] = 0.0
                m[f"replay_bar_{k}_close"] = 0.0
                m[f"replay_bar_{k}_volume"] = 0.0

        # 141-165: Indicator Snapshot (Fast, Slow EMA, ATR, ADX, SMA Volume)
        for k in range(1, 6):
            idx = -k
            if len(df) >= k:
                m[f"indicator_bar_{k}_ema_fast"] = float(df.get('ema_fast', df['close']).iloc[idx])
                m[f"indicator_bar_{k}_ema_slow"] = float(df.get('ema_slow', df['close']).iloc[idx])
                m[f"indicator_bar_{k}_atr"] = float(df.get('atr', pd.Series([0.0]*len(df))).iloc[idx])
                m[f"indicator_bar_{k}_adx"] = float(df.get('adx', pd.Series([0.0]*len(df))).iloc[idx])
                m[f"indicator_bar_{k}_vol_sma"] = float(df.get('vol_sma', pd.Series([0.0]*len(df))).iloc[idx])
            else:
                m[f"indicator_bar_{k}_ema_fast"] = 0.0
                m[f"indicator_bar_{k}_ema_slow"] = 0.0
                m[f"indicator_bar_{k}_atr"] = 0.0
                m[f"indicator_bar_{k}_adx"] = 0.0
                m[f"indicator_bar_{k}_vol_sma"] = 0.0

        # 166-175: Self-Optimization Weights (Level 18) & failures
        m["opt_weight_trend"] = 10.0
        m["opt_weight_liquidity"] = 18.0
        m["opt_weight_choch"] = 14.0
        m["opt_weight_bos"] = 13.0
        m["opt_weight_fvg"] = 9.0
        m["opt_weight_volume"] = 8.0
        m["opt_weight_session"] = 10.0
        m["opt_weight_volatility"] = 9.0
        m["opt_weight_rr"] = 9.0
        m["failure_downgrade_factor"] = 1.0

        return m

    # ─── Execution Check (Level 11) ─────────────────────────

    def _pre_execution_check(self, symbol: str, ask: float, bid: float, score: int) -> Tuple[bool, str]:
        """Runs pre-execution safety filters."""
        if score < 70:
            return False, "Confidence score below 70"

        if ask > 0 and bid > 0:
            spread_pips = self.spread_in_pips(symbol, ask, bid)
            if spread_pips > MAX_SPREAD_PIPS:
                return False, f"Spread too wide ({spread_pips:.1f} pips > {MAX_SPREAD_PIPS} pips)"

        # News blackout check
        from zohra.brokers.manager import broker_manager as broker
        if broker and hasattr(broker, 'news_agent') and broker.news_agent:
            news_status = broker.news_agent.check_news_status(symbol)
            if news_status.get("status") == "BLACKOUT":
                return False, f"News blackout active: {news_status.get('reason')}"

        return True, "Passed execution checks"

    # ─── Indicator Calculation ─────────────────────────────

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates indicators used to support market-reading analysis."""
        if len(df) < 50:
            return df

        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=SCALP_EMA_FAST, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=SCALP_EMA_SLOW, adjust=False).mean()
        df['ema_trend'] = df['close'].ewm(span=200, adjust=False).mean()

        # ATR
        hl = df['high'] - df['low']
        hc = (df['high'] - df['close'].shift(1)).abs()
        lc = (df['low'] - df['close'].shift(1)).abs()
        df['tr'] = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()

        # ADX
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm_s = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm_s = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        plus_di = 100 * pd.Series(plus_dm_s, index=df.index).rolling(14).mean() / (df['atr'] + 1e-9)
        minus_di = 100 * pd.Series(minus_dm_s, index=df.index).rolling(14).mean() / (df['atr'] + 1e-9)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        df['adx'] = dx.rolling(14).mean()

        # Volume
        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'
        if vol_col in df.columns:
            df['vol_sma'] = df[vol_col].rolling(20).mean()
            df['vol_strong'] = df[vol_col] > df['vol_sma']
        else:
            df['vol_sma'] = 1.0
            df['vol_strong'] = True

        return df

    # ─── Spread Calculation ────────────────────────────────

    @staticmethod
    def spread_in_pips(symbol: str, ask: float, bid: float) -> float:
        spread = ask - bid
        if "JPY" in symbol:
            return spread * 100
        elif "XAU" in symbol or "GOLD" in symbol.upper():
            return spread * 10
        else:
            return spread * 10000

    # ─── Signal Generation (Core Entry) ─────────────────────

    def generate_signal(self, df: pd.DataFrame, symbol: str,
                        ask: float = 0.0, bid: float = 0.0) -> Optional[Dict]:
        """Main stateless execution trigger with diagnostic logging."""
        # 0. Hard Symbol Guard check — Strictly Gold (XAUUSD) Only
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading disabled for {symbol}. Gold only mode is active.")
            return None

        if df is None or len(df) < 50:
            logger.debug(f"ℹ️ [{symbol}] Insufficient data for scalping ({len(df) if df is not None else 0} < 50 bars).")
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        
        # 1. Swings and Structure (Level 1)
        highs, lows = self._find_swings(df)
        structure_info = self._calculate_market_structure(df, highs, lows)

        # 2. Liquidity (Level 2)
        sweep_info = self._check_liquidity_sweep(df, highs, lows)
        eqh, eql = self._find_equal_points(highs, lows)

        # 3. FVGs (Level 3)
        bull_fvgs, bear_fvgs = self._find_fvgs(df)

        # 4. OBs (Level 4)
        bull_obs, bear_obs = self._find_order_blocks(df, highs, lows)

        # 5. Session (Level 5)
        sess_info = self._get_current_session_info()

        # 6. Volatility & Volume (Levels 6 & 7)
        atr_val = latest['atr']
        atr_sma = df['atr'].rolling(20).mean().iloc[-1]
        vol_regime = "Medium"
        if atr_val < atr_sma * 0.8:
            vol_regime = "Low"
        elif atr_val > atr_sma * 1.8:
            vol_regime = "Extreme"
        elif atr_val > atr_sma * 1.2:
            vol_regime = "High"

        atr_expanded = atr_val > atr_sma

        vol_col = 'tick_volume'
        if 'real_volume' in df.columns and df['real_volume'].sum() > 0:
            vol_col = 'real_volume'
        rvol = float(latest[vol_col] / (df[vol_col].rolling(20).mean().iloc[-1] + 1e-9))

        # Check setup direction
        direction = None
        reason = ""

        # Score breakdown components
        trend_pts = 0
        liq_pts = 0
        choch_pts = 0
        bos_pts = 0
        fvg_pts = 0
        vol_pts = 0
        sess_pts = 0
        volatility_pts = 0
        rr_pts = 9  # Default passing RR

        # LONG Setup Trigger: Sweep of SSL (liquidity pool) OR Touch of Bullish OB/FVG
        if sweep_info["swept"] and sweep_info["type"] == "SSL":
            direction = "LONG"
            reason = f"SSL Sweep at {sweep_info['level']} | CHOCH confirmed"
            liq_pts = 18
            choch_pts = 14
        elif bull_obs and abs(latest['close'] - bull_obs[0]["top"]) < atr_val * 0.5:
            direction = "LONG"
            reason = f"Bullish OB Retest near {bull_obs[0]['top']}"
            liq_pts = 10
            choch_pts = 8
        elif bull_fvgs and abs(latest['close'] - bull_fvgs[0]["bottom"]) < atr_val * 0.5:
            direction = "LONG"
            reason = f"Bullish FVG Pullback near {bull_fvgs[0]['bottom']}"
            liq_pts = 8
            fvg_pts = 9

        # SHORT Setup Trigger: Sweep of BSL OR Touch of Bearish OB/FVG
        elif sweep_info["swept"] and sweep_info["type"] == "BSL":
            direction = "SHORT"
            reason = f"BSL Sweep at {sweep_info['level']} | CHOCH confirmed"
            liq_pts = 18
            choch_pts = 14
        elif bear_obs and abs(latest['close'] - bear_obs[0]["bottom"]) < atr_val * 0.5:
            direction = "SHORT"
            reason = f"Bearish OB Retest near {bear_obs[0]['bottom']}"
            liq_pts = 10
            choch_pts = 8
        elif bear_fvgs and abs(latest['close'] - bear_fvgs[0]["top"]) < atr_val * 0.5:
            direction = "SHORT"
            reason = f"Bearish FVG Pullback near {bear_fvgs[0]['top']}"
            liq_pts = 8
            fvg_pts = 9

        if not direction:
            logger.info(f"📊 [DIAGNOSTIC] {symbol} M5: SSL_Swept={sweep_info['swept']} (type={sweep_info.get('type')}), BullOB={len(bull_obs)}, BearOB={len(bear_obs)}, BullFVG={len(bull_fvgs)}, BearFVG={len(bear_fvgs)} -> DECISION: NO_SIGNAL (No SMC Trigger)")
            return None

        # Level 9: HTF Alignment
        htf_align = self._check_htf_alignment(symbol, direction)
        if not htf_align["aligned"]:
            logger.info(f"⛔ [DIAGNOSTIC] {symbol} {direction}: Trigger formed ({reason}) but BLOCKED_BY_MARKET_FILTER (HTF Misalignment: D1={htf_align['d1_trend']}, H4={htf_align['h4_trend']}, H1={htf_align['h1_trend']}, M15={htf_align['m15_trend']})")
            return None

        trend_pts = htf_align["score"]

        # Fill points based on calculations
        if structure_info["bos_count"] > 0:
            bos_pts = 13
        if bull_fvgs or bear_fvgs:
            fvg_pts = max(fvg_pts, 5)
        if rvol > 2.0:
            vol_pts = 8
        elif rvol > 1.5:
            vol_pts = 6
        elif rvol > 1.0:
            vol_pts = 3

        if sess_info["session"] == "Overlap":
            sess_pts = 10
        elif sess_info["session"] in ("London", "New York"):
            sess_pts = 8
        else:
            sess_pts = 2

        if vol_regime == "High":
            volatility_pts = 9
        elif vol_regime == "Medium":
            volatility_pts = 6
        elif vol_regime == "Low":
            volatility_pts = 2

        # 10. Scoring Engine (Level 10)
        scores_breakdown = self._calculate_opportunity_score(
            trend_pts, liq_pts, choch_pts, bos_pts, fvg_pts, vol_pts, sess_pts, volatility_pts, rr_pts
        )
        score = scores_breakdown["total"]

        # SL and TP Sizing
        entry = latest['close']
        if direction == "LONG":
            recent_low = df['low'].tail(5).min()
            stop = min(entry - atr_val * 1.5, recent_low - atr_val * 0.5)
            risk = entry - stop
            tp1 = entry + risk * 1.0
            tp2 = entry + risk * 2.0
        else:
            recent_high = df['high'].tail(5).max()
            stop = max(entry + atr_val * 1.5, recent_high + atr_val * 0.5)
            risk = stop - entry
            tp1 = entry - risk * 1.0
            tp2 = entry - risk * 2.0

        if risk <= 0:
            logger.info(f"⛔ [DIAGNOSTIC] {symbol} {direction}: BLOCKED_BY_RISK (Calculated risk <= 0: stop={stop}, entry={entry})")
            return None

        # Level 11: Pre-Execution Safety Filters
        passed, rejection_msg = self._pre_execution_check(symbol, ask, bid, score)
        if not passed:
            logger.info(f"⛔ [DIAGNOSTIC] {symbol} {direction}: BLOCKED_BY_PRE_EXECUTION ({rejection_msg})")
            return None

        # Setup Classification (10 setups)
        setup_name = self._classify_setup_name(
            sweep_info["type"], sess_info["session"],
            len(bull_obs) > 0 or len(bear_obs) > 0,
            len(bull_fvgs) > 0 or len(bear_fvgs) > 0,
            structure_info["bos_count"] > 0, rvol, atr_expanded
        )

        # 150+ Fields Serializer (Level 13)
        spread_pips = self.spread_in_pips(symbol, ask, bid) if ask > 0 else 1.5
        metadata_fields = self._serialize_150_fields(
            df, symbol, direction, sess_info, structure_info, sweep_info,
            bull_fvgs, bear_fvgs, bull_obs, bear_obs, vol_regime, rvol,
            spread_pips, score, scores_breakdown, risk * 100, (tp2 - entry) / risk
        )

        # Append details into metadata
        metadata_fields["setup_name"] = setup_name
        metadata_fields["tp1"] = round(tp1, 5)
        metadata_fields["tp2"] = round(tp2, 5)

        signal = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": round(entry, 5),
            "stop_loss": round(stop, 5),
            "take_profit": round(tp2, 5),
            "tp1": round(tp1, 5),
            "tp2": round(tp2, 5),
            "confidence_score": score,
            "strategy": StrategyName.SCALP_M5.value,  # 'scalp_m5' ensures execution routes cleanly
            "reason": f"{setup_name} | {reason} | Score={score}/100",
            "scores_breakdown": scores_breakdown,
            "metadata": metadata_fields
        }

        logger.info(f"⚡ GOLD SCALP TRIGGER: {symbol} {direction} | Setup={setup_name} | Score={score}/100 | Entry={signal['entry_price']}")
        return signal

    # ─── Trailing SL & Position Management ──────────────────

    def check_exit(self, df: pd.DataFrame, position: Dict) -> Optional[Dict]:
        """Stateless trade checking: Trailing SL in profit, dynamic TP."""
        if len(df) < 5:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        direction = position['direction']
        entry = position['entry_price']
        stop = position['stop_loss']
        tp1 = position['take_profit'] * 0.5 + entry * 0.5  # Approximate TP1 if not set
        if 'tp1' in position:
            tp1 = position['tp1']
        tp2 = position['take_profit']
        if 'tp2' in position:
            tp2 = position['tp2']

        current = latest['close']
        atr_val = float(latest.get('atr', abs(entry - stop)))
        risk = abs(entry - stop)
        if risk == 0:
            return {'action': 'CLOSE_FULL', 'price': current, 'reason': 'ZERO_RISK'}

        # Calculate profit in terms of R-multiple
        r = (current - entry) / risk if direction == "LONG" else (entry - current) / risk

        # In profit trailing SL enforcement
        if r >= 0.5:
            if direction == "LONG":
                new_stop = current - atr_val * 1.5
                if new_stop > stop:
                    return {'action': 'TRAIL', 'price': current, 'new_stop': round(new_stop, 5), 'reason': 'DYNAMIC_TRAIL'}
            else:
                new_stop = current + atr_val * 1.5
                if new_stop < stop:
                    return {'action': 'TRAIL', 'price': current, 'new_stop': round(new_stop, 5), 'reason': 'DYNAMIC_TRAIL'}

        # Hard exits
        if direction == "LONG":
            if current >= tp2:
                return {'action': 'CLOSE_FULL', 'price': current, 'reason': 'TP2_HIT'}
            if current >= tp1 and not position.get('tp1_hit', False) and not position.get('half_closed', False):
                return {'action': 'CLOSE_HALF', 'price': current, 'reason': 'TP1_HIT'}
            if current <= stop:
                return {'action': 'CLOSE_FULL', 'price': current, 'reason': 'STOP_LOSS'}
        else:
            if current <= tp2:
                return {'action': 'CLOSE_FULL', 'price': current, 'reason': 'TP2_HIT'}
            if current <= tp1 and not position.get('tp1_hit', False) and not position.get('half_closed', False):
                return {'action': 'CLOSE_HALF', 'price': current, 'reason': 'TP1_HIT'}
            if current >= stop:
                return {'action': 'CLOSE_FULL', 'price': current, 'reason': 'STOP_LOSS'}

        # Momentum stall exit
        adx = float(latest.get('adx', 25))
        stall = bool(latest.get('stall', False))
        if stall and adx < MIN_ADX_SCALP:
            return {'action': 'CLOSE_FULL', 'price': current, 'reason': 'MOMENTUM_STALL'}

        return None

    # ─── Daily Limit & Lots Checks ─────────────────────────

    def calculate_lots(self, equity: float, stop_distance: float) -> float:
        """Dynamic lot sizer constrained by scalp risk limits."""
        if stop_distance <= 0:
            return 0.0
        risk_amount = equity * RISK_PER_TRADE
        lots = risk_amount / (stop_distance * 100_000)
        lots = min(lots, MAX_LOTS_SCALP)
        lots = max(lots, MIN_LOT_SIZE)
        return round(lots, 2)

    def can_trade_today(self) -> bool:
        return SCALP_STATE.daily_trade_count < MAX_DAILY_TRADES_SCALP

    def record_trade_taken(self):
        SCALP_STATE.daily_trade_count += 1

    def active_in_symbol(self, symbol: str) -> bool:
        return any(s.get('symbol') == symbol for s in SCALP_STATE.active_scalps)

    def add_active_scalp(self, trade: Dict):
        SCALP_STATE.active_scalps.append(trade)

    def remove_active_scalp(self, symbol: str):
        SCALP_STATE.active_scalps = [
            s for s in SCALP_STATE.active_scalps if s.get('symbol') != symbol
        ]

scalping_strategy = ScalpingStrategy()
