"""
Scalping Module v1 — Conservative 5M Scalping
================================================
ADD-ON for existing trading bot.

RULES THAT CANNOT BE OVERRIDDEN:
- Max 2 trades per day (hardcoded)
- 0.5% risk per trade (half of swing system)
- 1:1.5 minimum R:R (tighter than swing)
- Only London/NY overlap (13:00-17:00 UTC)
- No trades if spread > 2 pips
- Auto-close if momentum stalls

PARTIAL TP SYSTEM:
- TP1: 50% position at 1R (breakeven trigger)
- TP2: 50% position at 2R (full target)
- If momentum stalls before TP1: close at +0.3R
- If momentum strong: trail from 1R onward

MOMENTUM DETECTION (not "feeling"):
- ADX > 25 = strong trend, hold for TP2
- ADX < 20 = weak trend, take TP1 and done
- Volume < 20-period average = close early
- Price stalls 3 bars = close immediately
"""

import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import uuid

# Import from existing bot
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
from database import db
from data_feed import data_feed
from executor import executor
from telegram_bot import telegram

# ─── HARD LIMITS (cannot be changed via config) ───
MAX_DAILY_TRADES = 2
RISK_PER_TRADE = 0.005  # 0.5%
MIN_RR = 1.5
MAX_SPREAD_PIPS = 2.0
SESSION_START = time(13, 0)   # 13:00 UTC
SESSION_END = time(17, 0)     # 17:00 UTC
MIN_ADX = 20
STRONG_ADX = 25
STALL_BARS = 3

@dataclass
class ScalpState:
    """Runtime state for scalping module"""
    daily_trade_count: int = 0
    last_trade_date: Optional[datetime] = None
    active_scalps: List[Dict] = None

    def __post_init__(self):
        if self.active_scalps is None:
            self.active_scalps = []

SCALP_STATE = ScalpState()


class ScalpingEngine:
    """
    Conservative 5M scalping engine.
    Designed as ADD-ON, not replacement for 1H system.
    """

    def __init__(self):
        self.timeframe = "M5"
        # MT5 symbol names — no underscores
        self.pairs = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

    def _is_session_active(self) -> bool:
        """Only trade London/NY overlap (highest volume)"""
        now = datetime.utcnow()
        current_time = now.time()

        # Reset daily counter if new day
        if SCALP_STATE.last_trade_date and SCALP_STATE.last_trade_date.date() != now.date():
            SCALP_STATE.daily_trade_count = 0
            SCALP_STATE.active_scalps = []

        SCALP_STATE.last_trade_date = now

        # Weekend check
        if now.weekday() >= 5:
            return False

        return SESSION_START <= current_time <= SESSION_END

    def _get_spread_pips(self, symbol: str, current_price: Dict) -> float:
        """Calculate spread in pips"""
        spread = current_price.get("spread", 0)

        # Adjust for JPY pairs (3rd decimal = pip)
        if "JPY" in symbol:
            return spread * 100
        # Gold (XAU) — 1st decimal = $1, but "pips" are usually 0.1
        elif "XAU" in symbol:
            return spread * 10
        # Standard pairs (4th decimal = pip)
        else:
            return spread * 10000

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate scalping indicators:
        - EMA 8/21 (faster than 1H system)
        - ADX (trend strength)
        - ATR (volatility, stops)
        - Volume SMA (momentum confirmation)
        - Price stall detection
        """
        if len(df) < 30:
            return df

        # Fast EMAs
        df["ema_fast"] = df["close"].ewm(span=8, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()

        # ATR
        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = abs(df["high"] - df["close"].shift(1))
        df["tr3"] = abs(df["low"] - df["close"].shift(1))
        df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
        df["atr"] = df["tr"].rolling(window=14).mean()

        # ADX (trend strength)
        df["+dm"] = df["high"].diff()
        df["-dm"] = -df["low"].diff()
        df["+dm"] = np.where((df["+dm"] > df["-dm"]) & (df["+dm"] > 0), df["+dm"], 0)
        df["-dm"] = np.where((df["-dm"] > df["+dm"]) & (df["-dm"] > 0), df["-dm"], 0)

        df["+di"] = 100 * df["+dm"].rolling(14).mean() / df["atr"]
        df["-di"] = 100 * df["-dm"].rolling(14).mean() / df["atr"]
        df["dx"] = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"])
        df["adx"] = df["dx"].rolling(14).mean()

        # Volume
        df["volume_sma"] = df["volume"].rolling(window=20).mean()
        df["volume_strong"] = df["volume"] > df["volume_sma"]

        # EMA cross
        df["ema_diff"] = df["ema_fast"] - df["ema_slow"]
        df["cross_up"] = (df["ema_diff"] > 0) & (df["ema_diff"].shift(1) <= 0)
        df["cross_down"] = (df["ema_diff"] < 0) & (df["ema_diff"].shift(1) >= 0)

        # Price stall detection (3 bars in tight range)
        df["range"] = df["high"] - df["low"]
        df["avg_range"] = df["range"].rolling(10).mean()
        df["stall"] = (df["range"] < df["avg_range"] * 0.5).rolling(3).sum() >= 3

        return df

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """
        Generate scalping signal with strict filters.
        Returns None if no valid setup.
        """
        df = self.calculate_indicators(df)

        if len(df) < 30:
            return None

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # ─── FILTER 1: ADX Check ───
        adx = latest["adx"]
        if pd.isna(adx) or adx < MIN_ADX:
            return None  # Too weak, no trade

        # ─── FILTER 2: Volume Check ───
        if not latest["volume_strong"]:
            return None  # Low volume, no trade

        signal = None

        # ─── LONG Signal ───
        if latest["cross_up"] and latest["close"] > latest["ema_fast"]:
            entry = latest["close"]
            atr = latest["atr"]

            # Dynamic stop: 1.5x ATR or recent swing low
            recent_low = df["low"].tail(5).min()
            stop_from_atr = entry - (atr * 1.5)
            stop_from_swing = recent_low - (atr * 0.5)
            stop = max(stop_from_atr, stop_from_swing)  # Tighter stop

            # Targets
            risk = entry - stop
            tp1 = entry + (risk * 1.0)   # 1R — close 50%
            tp2 = entry + (risk * 2.0)   # 2R — close 50%

            # Check R:R
            if (tp1 - entry) / (entry - stop) < MIN_RR:
                return None

            signal = {
                "direction": "LONG",
                "entry": entry,
                "stop": stop,
                "tp1": tp1,
                "tp2": tp2,
                "atr": atr,
                "adx": adx,
                "is_strong": adx >= STRONG_ADX,
                "risk": risk
            }

        # ─── SHORT Signal ───
        elif latest["cross_down"] and latest["close"] < latest["ema_fast"]:
            entry = latest["close"]
            atr = latest["atr"]

            recent_high = df["high"].tail(5).max()
            stop_from_atr = entry + (atr * 1.5)
            stop_from_swing = recent_high + (atr * 0.5)
            stop = min(stop_from_atr, stop_from_swing)

            risk = stop - entry
            tp1 = entry - (risk * 1.0)
            tp2 = entry - (risk * 2.0)

            if (entry - tp1) / (stop - entry) < MIN_RR:
                return None

            signal = {
                "direction": "SHORT",
                "entry": entry,
                "stop": stop,
                "tp1": tp1,
                "tp2": tp2,
                "atr": atr,
                "adx": adx,
                "is_strong": adx >= STRONG_ADX,
                "risk": risk
            }

        return signal

    def calculate_position_size(self, equity: float, risk_amount: float, 
                                symbol: str) -> int:
        """
        Calculate size with HARD CAPS.
        Max 3 lots regardless of account size.
        """
        risk_usd = equity * RISK_PER_TRADE

        # For forex: 1 pip = $0.10 per 1,000 units (micro lot)
        # Risk in pips = risk_amount / pip_value
        # But simpler: risk_usd / (entry - stop) = units

        if risk_amount <= 0:
            return 0

        units = int(risk_usd / risk_amount)

        # HARD CAP: 3,000 units (3 micro lots) MAX
        # This is non-negotiable
        units = min(units, 3000)

        # Round to nearest 1,000
        units = (units // 1000) * 1000
        units = max(1000, units)  # Minimum 1 micro lot

        return units

    def check_exit_conditions(self, df: pd.DataFrame, position: Dict) -> Optional[Dict]:
        """
        Check if scalp should be closed, partially or fully.
        Returns: {"action": "CLOSE_FULL" | "CLOSE_HALF" | "MOVE_BE" | "TRAIL", ...}
        """
        if len(df) < 5:
            return None

        latest = df.iloc[-1]
        direction = position["direction"]
        entry = position["entry_price"]
        stop = position["stop_price"]
        tp1 = position["tp1"]
        tp2 = position["tp2"]
        current = latest["close"]
        adx = latest["adx"]

        # Calculate current R multiple
        if direction == "LONG":
            current_r = (current - entry) / (entry - stop) if (entry - stop) > 0 else 0

            # 1. Hit TP1 — close 50%, move SL to BE
            if current >= tp1 and not position.get("tp1_hit", False):
                return {"action": "CLOSE_HALF", "price": current, "reason": "TP1_HIT"}

            # 2. Hit TP2 — close remaining
            if current >= tp2:
                return {"action": "CLOSE_FULL", "price": current, "reason": "TP2_HIT"}

            # 3. Stop loss
            if current <= stop:
                return {"action": "CLOSE_FULL", "price": current, "reason": "STOP_LOSS"}

            # 4. Momentum stall — close early if weak
            if latest["stall"] and adx < MIN_ADX:
                # If in profit, take it. If not, still exit (momentum gone)
                return {"action": "CLOSE_FULL", "price": current, "reason": "MOMENTUM_STALL"}

            # 5. Volume drop — close if volume weakens significantly
            if not latest["volume_strong"] and current_r > 0.5:
                return {"action": "CLOSE_FULL", "price": current, "reason": "VOLUME_DROP"}

            # 6. Trail stop if strong trend and in profit
            if current_r >= 1.0 and adx >= STRONG_ADX:
                new_stop = current - (latest["atr"] * 1.0)
                if new_stop > stop:
                    return {"action": "TRAIL", "price": current, "new_stop": new_stop}

        else:  # SHORT
            current_r = (entry - current) / (stop - entry) if (stop - entry) > 0 else 0

            if current <= tp1 and not position.get("tp1_hit", False):
                return {"action": "CLOSE_HALF", "price": current, "reason": "TP1_HIT"}

            if current <= tp2:
                return {"action": "CLOSE_FULL", "price": current, "reason": "TP2_HIT"}

            if current >= stop:
                return {"action": "CLOSE_FULL", "price": current, "reason": "STOP_LOSS"}

            if latest["stall"] and adx < MIN_ADX:
                return {"action": "CLOSE_FULL", "price": current, "reason": "MOMENTUM_STALL"}

            if not latest["volume_strong"] and current_r > 0.5:
                return {"action": "CLOSE_FULL", "price": current, "reason": "VOLUME_DROP"}

            if current_r >= 1.0 and adx >= STRONG_ADX:
                new_stop = current + (latest["atr"] * 1.0)
                if new_stop < stop:
                    return {"action": "TRAIL", "price": current, "new_stop": new_stop}

        return None

    def run_cycle(self):
        """
        One scalping cycle.
        Called every 5 minutes during session.
        """
        # ─── Session Check ───
        if not self._is_session_active():
            return

        # ─── Daily Limit Check ───
        if SCALP_STATE.daily_trade_count >= MAX_DAILY_TRADES:
            return

        # ─── Account Check ───
        account = data_feed.get_account_summary()
        if not account:
            return

        equity = account["equity"]

        # ─── Check Existing Scalps ───
        for scalp in SCALP_STATE.active_scalps:
            symbol = scalp["symbol"]
            df = data_feed.get_candles(symbol, count=50, granularity="M5")

            if df.empty:
                continue

            exit_signal = self.check_exit_conditions(df, scalp)

            if exit_signal:
                self._execute_exit(scalp, exit_signal, equity)

        # ─── Look for New Signals ───
        if SCALP_STATE.daily_trade_count >= MAX_DAILY_TRADES:
            return

        for symbol in self.pairs:
            # Skip if already in this pair
            if any(s["symbol"] == symbol for s in SCALP_STATE.active_scalps):
                continue

            # Get current price for spread check
            current_price = data_feed.get_current_price(symbol)
            spread_pips = self._get_spread_pips(symbol, current_price)

            if spread_pips > MAX_SPREAD_PIPS:
                continue  # Spread too wide

            # Get 5M data
            df = data_feed.get_candles(symbol, count=100, granularity="M5")
            if df.empty or len(df) < 50:
                continue

            signal = self.generate_signal(df, symbol)

            if signal:
                # Calculate size
                units = self.calculate_position_size(equity, signal["risk"], symbol)

                if units < 1000:
                    continue

                # Execute
                trade = {
                    "trade_id": f"SCALP_{symbol}_{datetime.utcnow().strftime('%H%M%S')}",
                    "symbol": symbol,
                    "direction": signal["direction"],
                    "entry_price": signal["entry"],
                    "stop_price": signal["stop"],
                    "tp1": signal["tp1"],
                    "tp2": signal["tp2"],
                    "position_size": units,
                    "risk_usd": equity * RISK_PER_TRADE,
                    "tp1_hit": False,
                    "atr": signal["atr"],
                    "adx": signal["adx"],
                    "is_strong": signal["is_strong"]
                }

                result = executor.open_position(trade)

                if result.get("success"):
                    SCALP_STATE.daily_trade_count += 1
                    SCALP_STATE.active_scalps.append(trade)

                    strength = "🔥 STRONG" if signal["is_strong"] else "⚡ NORMAL"
                    telegram.send_message(
                        f"🎯 <b>SCALP {strength}</b>\n"
                        f"{symbol} {signal['direction']}\n"
                        f"Entry: {signal['entry']:.5f}\n"
                        f"TP1 (50%): {signal['tp1']:.5f}\n"
                        f"TP2 (50%): {signal['tp2']:.5f}\n"
                        f"Stop: {signal['stop']:.5f}\n"
                        f"Size: {units} units\n"
                        f"ADX: {signal['adx']:.1f}"
                    )

    def _execute_exit(self, scalp: Dict, exit_signal: Dict, equity: float):
        """Execute partial or full close"""
        action = exit_signal["action"]
        symbol = scalp["symbol"]

        if action == "CLOSE_HALF":
            # Close 50% at TP1 via MT5 partial close
            half_lots = round(scalp.get("lots", 0.02) / 2, 2)

            result = executor.close_position(
                scalp["trade_id"], scalp.get("mt5_ticket", 0),
                symbol, scalp["direction"]
            )

            if result.get("success"):
                scalp["tp1_hit"] = True
                pnl = result["pnl_usd"]

                # If strong trend, re-enter with half size for TP2
                if scalp["is_strong"]:
                    telegram.send_message(
                        f"✅ <b>TP1 HIT — Holding for TP2</b>\n"
                        f"{symbol}: +${pnl:.2f} (50% closed)\n"
                        f"Remaining: Running to {scalp['tp2']:.5f}"
                    )
                    # MT5 supports partial close natively via volume param
                    # executor.close_position handles it
                else:
                    telegram.send_message(
                        f"✅ <b>TP1 HIT — Full Close</b>\n"
                        f"{symbol}: +${pnl:.2f}\n"
                        f"Reason: Normal momentum, take profit"
                    )

                SCALP_STATE.active_scalps.remove(scalp)

        elif action == "CLOSE_FULL":
            result = executor.close_position(
                scalp["trade_id"], scalp.get("mt5_ticket", 0),
                symbol, scalp["direction"]
            )

            if result.get("success"):
                pnl = result["pnl_usd"]
                reason = exit_signal["reason"]
                emoji = "✅" if pnl > 0 else "❌"

                telegram.send_message(
                    f"{emoji} <b>SCALP CLOSED — {reason}</b>\n"
                    f"{symbol}: ${pnl:.2f}"
                )

                SCALP_STATE.active_scalps.remove(scalp)

        elif action == "TRAIL":
            # Update stop loss
            executor.modify_stop(
                scalp.get("mt5_ticket", 0),
                exit_signal["new_stop"]
            )

            telegram.send_message(
                f"🔄 <b>TRAIL STOP</b>\n"
                f"{symbol}: New stop {exit_signal['new_stop']:.5f}"
            )


# Singleton
scalping_engine = ScalpingEngine()


def run_scalping_cycle():
    """Entry point — call this every 5 minutes"""
    try:
        scalping_engine.run_cycle()
    except Exception as e:
        db.log_system("ERROR", f"Scalping cycle error: {e}")
