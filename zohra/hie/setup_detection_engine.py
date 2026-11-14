"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 3 — SETUP DETECTION ENGINE                                  ║
║   Detects historical occurrences of SMC, Technical, and Scalping    ║
║   setups from stored candle data. Saves to hie_setups table.        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
import threading
import datetime as dt
from typing import List, Optional, Dict, Any

import pandas as pd
import numpy as np

logger = logging.getLogger("zohra.hie.setup_detection")

# ────────────────────────────────────────────────────────────────
#  SESSION CLASSIFIER (UTC hour → session name)
# ────────────────────────────────────────────────────────────────

def _classify_session(ts) -> str:
    """Classify a UTC timestamp into a trading session."""
    if isinstance(ts, str):
        ts = pd.to_datetime(ts, utc=True)
    hour = ts.hour if hasattr(ts, 'hour') else 0
    if 22 <= hour or hour < 8:
        return "Asian"
    elif 8 <= hour < 12:
        return "London"
    elif 12 <= hour < 17:
        return "NewYork"
    else:
        return "Overlap"


# ────────────────────────────────────────────────────────────────
#  INDICATOR HELPERS
# ────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


# ────────────────────────────────────────────────────────────────
#  SETUP DETECTION ENGINE
# ────────────────────────────────────────────────────────────────

class SetupDetectionEngine:
    """
    Scans historical candle data and detects trade setups.
    Results are stored in hie_setups table in hie_data.db.
    """

    SETUP_TYPES = [
        "BOS", "CHOCH", "MSS", "FVG", "LiquiditySweep", "OrderBlock",
        "EMACross", "TrendPullback", "Breakout", "RSIDivergence",
        "MACDConfirm", "MomentumBreakout", "MitigationBlock",
        "TrendlineContinuation", "SessionBreakout", "MarketStructureShift",
        "RangeExpansion"
    ]

    def __init__(self):
        from zohra.hie.historical_data_engine import historical_data_engine
        self._hde = historical_data_engine
        self._db_path = historical_data_engine.db_path_hie
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_table()

    def _init_table(self):
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_setups (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT NOT NULL,
                    timeframe   TEXT NOT NULL,
                    setup_type  TEXT NOT NULL,
                    direction   TEXT NOT NULL,
                    session     TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss   REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    atr         REAL DEFAULT 0,
                    outcome_analyzed INTEGER DEFAULT 0,
                    UNIQUE(symbol, timeframe, setup_type, direction, timestamp)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hie_setups_sym ON hie_setups(symbol, timeframe, setup_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hie_setups_session ON hie_setups(session)")
            conn.commit()
        except Exception as e:
            logger.error(f"SetupDetectionEngine init error: {e}")
        finally:
            if conn:
                conn.close()

    # ──────────────────────────────────────────────
    #  BACKGROUND SCAN
    # ──────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-SetupDetect")
        self._thread.start()
        logger.info("🔍 HIE Setup Detection Engine started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Scan all symbols once, then refresh hourly."""
        from zohra.hie.historical_data_engine import HIE_SYMBOLS
        timeframes = ["M15", "H1", "H4"]

        # Initial full scan
        for symbol in HIE_SYMBOLS:
            if not self._running:
                break
            for tf in timeframes:
                if not self._running:
                    break
                self.detect_and_store(symbol, tf)

        # Hourly refresh
        while self._running:
            import time
            time.sleep(3600)
            for symbol in HIE_SYMBOLS:
                if not self._running:
                    break
                self.detect_and_store(symbol, "H1")

    # ──────────────────────────────────────────────
    #  DETECTION + STORAGE
    # ──────────────────────────────────────────────

    def detect_and_store(self, symbol: str, timeframe: str) -> int:
        """Run all detectors on stored candles for symbol+tf. Returns count saved."""
        try:
            df = self._hde.get_candles(symbol, timeframe, limit=5000)
            if df.empty or len(df) < 50:
                return 0
            setups = self.detect_setups(symbol, timeframe, df)
            return self._store_setups(setups)
        except Exception as e:
            logger.error(f"SetupDetection error {symbol}/{timeframe}: {e}")
            return 0

    def detect_setups(self, symbol: str, timeframe: str, df: pd.DataFrame) -> List[Dict]:
        """Run all detectors and return combined setup list."""
        all_setups = []
        detectors = [
            self._detect_bos, self._detect_choch, self._detect_fvg,
            self._detect_order_block, self._detect_liquidity_sweep,
            self._detect_ema_cross, self._detect_trend_pullback,
            self._detect_breakout, self._detect_rsi_divergence,
            self._detect_momentum_breakout, self._detect_mitigation_block,
            self._detect_trendline_continuation, self._detect_session_breakout,
            self._detect_market_structure_shift, self._detect_range_expansion
        ]
        for detector in detectors:
            try:
                setups = detector(symbol, timeframe, df)
                all_setups.extend(setups)
            except Exception as e:
                logger.debug(f"Detector {detector.__name__} error: {e}")
        return all_setups

    # ──────────────────────────────────────────────
    #  SMC DETECTORS
    # ──────────────────────────────────────────────

    def _detect_bos(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Break of Structure — price breaks a previous swing high/low."""
        setups = []
        atr_series = _atr(df)
        highs = df["high"].rolling(10).max().shift(1)
        lows = df["low"].rolling(10).min().shift(1)

        for i in range(20, len(df) - 1):
            ts = str(df.index[i])
            row = df.iloc[i]
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])

            prev_high = float(highs.iloc[i]) if not pd.isna(highs.iloc[i]) else row["high"]
            prev_low = float(lows.iloc[i]) if not pd.isna(lows.iloc[i]) else row["low"]

            # Bullish BOS
            if row["close"] > prev_high and df["close"].iloc[i-1] <= prev_high:
                setups.append(self._make_setup(symbol, tf, "BOS", "LONG", session, ts,
                                               row["close"], row["close"] - atr * 1.5, row["close"] + atr * 2.5, atr))
            # Bearish BOS
            elif row["close"] < prev_low and df["close"].iloc[i-1] >= prev_low:
                setups.append(self._make_setup(symbol, tf, "BOS", "SHORT", session, ts,
                                               row["close"], row["close"] + atr * 1.5, row["close"] - atr * 2.5, atr))
        return setups

    def _detect_choch(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Change of Character — reversal of market structure."""
        setups = []
        atr_series = _atr(df)
        ema_fast = _ema(df["close"], 20)
        ema_slow = _ema(df["close"], 50)

        for i in range(55, len(df) - 1):
            ts = str(df.index[i])
            row = df.iloc[i]
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])

            prev_fast = float(ema_fast.iloc[i-1])
            curr_fast = float(ema_fast.iloc[i])
            prev_slow = float(ema_slow.iloc[i-1])
            curr_slow = float(ema_slow.iloc[i])

            # Bullish CHoCH — EMA20 crosses above EMA50 from below
            if prev_fast < prev_slow and curr_fast > curr_slow:
                setups.append(self._make_setup(symbol, tf, "CHOCH", "LONG", session, ts,
                                               row["close"], row["close"] - atr * 1.5, row["close"] + atr * 2.5, atr))
            # Bearish CHoCH
            elif prev_fast > prev_slow and curr_fast < curr_slow:
                setups.append(self._make_setup(symbol, tf, "CHOCH", "SHORT", session, ts,
                                               row["close"], row["close"] + atr * 1.5, row["close"] - atr * 2.5, atr))
        return setups

    def _detect_fvg(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Fair Value Gap — 3-candle imbalance pattern."""
        setups = []
        atr_series = _atr(df)

        for i in range(2, len(df) - 1):
            ts = str(df.index[i])
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])

            c0 = df.iloc[i-2]
            c2 = df.iloc[i]

            # Bullish FVG: gap between c0 high and c2 low
            if c0["high"] < c2["low"] and (c2["low"] - c0["high"]) > atr * 0.3:
                entry = c2["close"]
                setups.append(self._make_setup(symbol, tf, "FVG", "LONG", session, ts,
                                               entry, entry - atr * 1.5, entry + atr * 2.5, atr))
            # Bearish FVG
            elif c0["low"] > c2["high"] and (c0["low"] - c2["high"]) > atr * 0.3:
                entry = c2["close"]
                setups.append(self._make_setup(symbol, tf, "FVG", "SHORT", session, ts,
                                               entry, entry + atr * 1.5, entry - atr * 2.5, atr))
        return setups

    def _detect_order_block(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Order Block — last opposite candle before a strong move."""
        setups = []
        atr_series = _atr(df)
        momentum_threshold = 1.5

        for i in range(5, len(df) - 2):
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            ts = str(df.index[i+1])
            session = _classify_session(df.index[i+1])

            curr = df.iloc[i]
            nxt = df.iloc[i+1]
            move_size = abs(nxt["close"] - nxt["open"])

            if move_size < atr * momentum_threshold:
                continue

            # Bullish OB: bearish candle followed by strong bullish move
            if curr["close"] < curr["open"] and nxt["close"] > nxt["open"]:
                entry = nxt["close"]
                setups.append(self._make_setup(symbol, tf, "OrderBlock", "LONG", session, ts,
                                               entry, curr["low"] - atr * 0.3, entry + atr * 2.5, atr))
            # Bearish OB: bullish candle followed by strong bearish move
            elif curr["close"] > curr["open"] and nxt["close"] < nxt["open"]:
                entry = nxt["close"]
                setups.append(self._make_setup(symbol, tf, "OrderBlock", "SHORT", session, ts,
                                               entry, curr["high"] + atr * 0.3, entry - atr * 2.5, atr))
        return setups

    def _detect_liquidity_sweep(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Liquidity Sweep — price spikes past a level then reverses sharply."""
        setups = []
        atr_series = _atr(df)
        lookback = 20

        for i in range(lookback, len(df) - 1):
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            ts = str(df.index[i])
            session = _classify_session(df.index[i])
            row = df.iloc[i]

            recent = df.iloc[i-lookback:i]
            swing_high = recent["high"].max()
            swing_low = recent["low"].min()

            # Bullish sweep: wick below swing low, close above
            if row["low"] < swing_low and row["close"] > swing_low and (row["high"] - row["low"]) > atr * 1.2:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "LiquiditySweep", "LONG", session, ts,
                                               entry, row["low"] - atr * 0.3, entry + atr * 2.5, atr))
            # Bearish sweep: wick above swing high, close below
            elif row["high"] > swing_high and row["close"] < swing_high and (row["high"] - row["low"]) > atr * 1.2:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "LiquiditySweep", "SHORT", session, ts,
                                               entry, row["high"] + atr * 0.3, entry - atr * 2.5, atr))
        return setups

    # ──────────────────────────────────────────────
    #  TECHNICAL DETECTORS
    # ──────────────────────────────────────────────

    def _detect_ema_cross(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """EMA 20/50 crossover signals."""
        setups = []
        atr_series = _atr(df)
        ema20 = _ema(df["close"], 20)
        ema50 = _ema(df["close"], 50)

        for i in range(51, len(df) - 1):
            if pd.isna(ema20.iloc[i]) or pd.isna(ema50.iloc[i]):
                continue
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            ts = str(df.index[i])
            session = _classify_session(df.index[i])
            row = df.iloc[i]

            # Golden cross
            if ema20.iloc[i-1] <= ema50.iloc[i-1] and ema20.iloc[i] > ema50.iloc[i]:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "EMACross", "LONG", session, ts,
                                               entry, entry - atr * 1.5, entry + atr * 2.5, atr))
            # Death cross
            elif ema20.iloc[i-1] >= ema50.iloc[i-1] and ema20.iloc[i] < ema50.iloc[i]:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "EMACross", "SHORT", session, ts,
                                               entry, entry + atr * 1.5, entry - atr * 2.5, atr))
        return setups

    def _detect_trend_pullback(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Price pullback to EMA in an established trend."""
        setups = []
        atr_series = _atr(df)
        ema100 = _ema(df["close"], 100)

        for i in range(100, len(df) - 1):
            if pd.isna(ema100.iloc[i]):
                continue
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            ts = str(df.index[i])
            session = _classify_session(df.index[i])
            row = df.iloc[i]
            ema_val = float(ema100.iloc[i])

            # Bullish pullback: trend up, price touches EMA and bounces
            if row["close"] > ema_val and abs(row["low"] - ema_val) < atr * 0.5:
                if df.iloc[i-1]["close"] < df.iloc[i]["close"]:
                    entry = row["close"]
                    setups.append(self._make_setup(symbol, tf, "TrendPullback", "LONG", session, ts,
                                                   entry, ema_val - atr * 0.5, entry + atr * 2.5, atr))
            # Bearish pullback
            elif row["close"] < ema_val and abs(row["high"] - ema_val) < atr * 0.5:
                if df.iloc[i-1]["close"] > df.iloc[i]["close"]:
                    entry = row["close"]
                    setups.append(self._make_setup(symbol, tf, "TrendPullback", "SHORT", session, ts,
                                                   entry, ema_val + atr * 0.5, entry - atr * 2.5, atr))
        return setups

    def _detect_breakout(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Range breakout — price closes outside a 20-bar range."""
        setups = []
        atr_series = _atr(df)
        lookback = 20

        for i in range(lookback, len(df) - 1):
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            ts = str(df.index[i])
            session = _classify_session(df.index[i])
            row = df.iloc[i]
            prev = df.iloc[i-lookback:i]

            range_high = prev["high"].max()
            range_low = prev["low"].min()
            range_size = range_high - range_low

            if range_size < atr * 1.5:  # Only trade meaningful ranges
                continue

            if row["close"] > range_high:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "Breakout", "LONG", session, ts,
                                               entry, range_high - atr * 0.5, entry + atr * 3.0, atr))
            elif row["close"] < range_low:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "Breakout", "SHORT", session, ts,
                                               entry, range_low + atr * 0.5, entry - atr * 3.0, atr))
        return setups

    def _detect_rsi_divergence(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """RSI divergence — price makes new high/low but RSI does not."""
        setups = []
        atr_series = _atr(df)
        rsi = _rsi(df["close"], 14)

        for i in range(20, len(df) - 1):
            if pd.isna(rsi.iloc[i]):
                continue
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            ts = str(df.index[i])
            session = _classify_session(df.index[i])
            row = df.iloc[i]

            # Look for divergence over last 10 bars
            window = slice(i-10, i)
            price_high = df["high"].iloc[window].max()
            price_low = df["low"].iloc[window].min()
            rsi_high = rsi.iloc[window].max()
            rsi_low = rsi.iloc[window].min()

            # Bearish divergence: price makes new high, RSI lower high
            if row["high"] >= price_high and float(rsi.iloc[i]) < rsi_high - 5 and float(rsi.iloc[i]) > 60:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "RSIDivergence", "SHORT", session, ts,
                                               entry, entry + atr * 1.5, entry - atr * 2.5, atr))
            # Bullish divergence: price makes new low, RSI higher low
            elif row["low"] <= price_low and float(rsi.iloc[i]) > rsi_low + 5 and float(rsi.iloc[i]) < 40:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "RSIDivergence", "LONG", session, ts,
                                               entry, entry - atr * 1.5, entry + atr * 2.5, atr))
        return setups

    def _detect_momentum_breakout(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """High-momentum breakout: large candle body with volume spike."""
        setups = []
        atr_series = _atr(df)

        if "volume" not in df.columns:
            return setups

        vol_sma = df["volume"].rolling(20).mean()

        for i in range(20, len(df) - 1):
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            ts = str(df.index[i])
            session = _classify_session(df.index[i])
            row = df.iloc[i]

            body = abs(row["close"] - row["open"])
            vol = float(row.get("volume", 0))
            avg_vol = float(vol_sma.iloc[i]) if not pd.isna(vol_sma.iloc[i]) else 0

            if body < atr * 1.5:
                continue
            if avg_vol > 0 and vol < avg_vol * 1.3:
                continue  # Needs volume confirmation

            if row["close"] > row["open"]:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "MomentumBreakout", "LONG", session, ts,
                                               entry, entry - atr * 1.2, entry + atr * 2.0, atr))
            else:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "MomentumBreakout", "SHORT", session, ts,
                                               entry, entry + atr * 1.2, entry - atr * 2.0, atr))
        return setups

    def _detect_mitigation_block(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Mitigation Block (SMC) — pullback to a broken order block / failed swing level."""
        setups = []
        atr_series = _atr(df)
        lookback = 15

        for i in range(lookback + 2, len(df) - 1):
            ts = str(df.index[i])
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])
            row = df.iloc[i]
            
            # Simple logic: detect a previous swing high/low that was breached aggressively
            recent = df.iloc[i-lookback:i]
            swing_high = recent["high"].max()
            swing_low = recent["low"].min()
            
            # Pullback touch to the broken swing level
            # Bullish Mitigation Block: Price breaks below a previous swing low, then closes back above, and pulls back to that level
            if row["low"] <= swing_low and row["close"] > swing_low and abs(row["close"] - swing_low) < atr * 0.5:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "MitigationBlock", "LONG", session, ts,
                                               entry, entry - atr * 1.5, entry + atr * 2.5, atr))
            # Bearish Mitigation Block
            elif row["high"] >= swing_high and row["close"] < swing_high and abs(row["close"] - swing_high) < atr * 0.5:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "MitigationBlock", "SHORT", session, ts,
                                               entry, entry + atr * 1.5, entry - atr * 2.5, atr))
        return setups

    def _detect_trendline_continuation(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Trendline Continuation — bounce from a diagonal support/resistance trendline."""
        setups = []
        atr_series = _atr(df)
        
        for i in range(30, len(df) - 1):
            ts = str(df.index[i])
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])
            row = df.iloc[i]
            
            # Linear regression of close prices over last 20 bars to check trend direction & touch
            window = df["close"].iloc[i-20:i]
            x = np.arange(len(window))
            slope, intercept = np.polyfit(x, window.values, 1)
            
            # Predict trendline level
            pred_level = slope * len(x) + intercept
            
            # Touch with bounce
            # Bullish trendline continuation
            if slope > 0 and row["low"] <= pred_level + atr * 0.2 and row["close"] > pred_level:
                if df["close"].iloc[i-1] <= pred_level + atr * 0.5:
                    entry = row["close"]
                    setups.append(self._make_setup(symbol, tf, "TrendlineContinuation", "LONG", session, ts,
                                                   entry, entry - atr * 1.5, entry + atr * 2.5, atr))
            # Bearish trendline continuation
            elif slope < 0 and row["high"] >= pred_level - atr * 0.2 and row["close"] < pred_level:
                if df["close"].iloc[i-1] >= pred_level - atr * 0.5:
                    entry = row["close"]
                    setups.append(self._make_setup(symbol, tf, "TrendlineContinuation", "SHORT", session, ts,
                                                   entry, entry + atr * 1.5, entry - atr * 2.5, atr))
        return setups

    def _detect_session_breakout(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Session Breakout — high-volatility breakout of the Asian session high/low during London/NY open."""
        setups = []
        atr_series = _atr(df)
        
        for i in range(25, len(df) - 1):
            ts = str(df.index[i])
            time_dt = pd.to_datetime(df.index[i])
            hour = time_dt.hour
            
            # Only look for session open hours: London open (7-9 UTC) or NY open (12-14 UTC)
            if not ((7 <= hour <= 9) or (12 <= hour <= 14)):
                continue
                
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])
            row = df.iloc[i]
            
            # Find the range of the preceding 8 hours (Asian consolidation)
            prev_8h = df.iloc[i-20:i]
            range_high = prev_8h["high"].max()
            range_low = prev_8h["low"].min()
            
            # Breakout logic
            if row["close"] > range_high and df["close"].iloc[i-1] <= range_high:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "SessionBreakout", "LONG", session, ts,
                                               entry, range_high - atr * 0.8, entry + atr * 2.0, atr))
            elif row["close"] < range_low and df["close"].iloc[i-1] >= range_low:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "SessionBreakout", "SHORT", session, ts,
                                               entry, range_low + atr * 0.8, entry - atr * 2.0, atr))
        return setups

    def _detect_market_structure_shift(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Market Structure Shift (MSS) — breaking structural swing high/low in reverse direction."""
        setups = []
        atr_series = _atr(df)
        lookback = 12
        
        for i in range(lookback, len(df) - 1):
            ts = str(df.index[i])
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])
            row = df.iloc[i]
            
            recent = df.iloc[i-lookback:i]
            swing_high = recent["high"].max()
            swing_low = recent["low"].min()
            
            # Bullish MSS: Price breaks above the recent swing high after a downtrend
            if row["close"] > swing_high and df["close"].iloc[i-1] <= swing_high:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "MarketStructureShift", "LONG", session, ts,
                                               entry, entry - atr * 1.5, entry + atr * 2.5, atr))
            # Bearish MSS: Price breaks below the recent swing low after an uptrend
            elif row["close"] < swing_low and df["close"].iloc[i-1] >= swing_low:
                entry = row["close"]
                setups.append(self._make_setup(symbol, tf, "MarketStructureShift", "SHORT", session, ts,
                                               entry, entry + atr * 1.5, entry - atr * 2.5, atr))
        return setups

    def _detect_range_expansion(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict]:
        """Range Expansion — sudden volatility expansion (BB contraction followed by breakout)."""
        setups = []
        atr_series = _atr(df)
        
        # Calculate Bollinger Band Width
        sma = df["close"].rolling(20).mean()
        std = df["close"].rolling(20).std()
        bb_width = (std * 4) / (sma + 1e-9)
        
        for i in range(30, len(df) - 1):
            ts = str(df.index[i])
            atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.001
            session = _classify_session(df.index[i])
            row = df.iloc[i]
            
            # Squeeze: BB width in bottom 25% of recent 50 bars
            recent_widths = bb_width.iloc[i-50:i]
            squeeze_threshold = recent_widths.quantile(0.25)
            is_squeezed = bb_width.iloc[i-1] < squeeze_threshold
            
            # Expansion: sudden spike in BB width + price moves out
            if is_squeezed and bb_width.iloc[i] > bb_width.iloc[i-1] * 1.25:
                # Bullish expansion
                if row["close"] > row["open"]:
                    entry = row["close"]
                    setups.append(self._make_setup(symbol, tf, "RangeExpansion", "LONG", session, ts,
                                                   entry, entry - atr * 1.5, entry + atr * 2.5, atr))
                # Bearish expansion
                else:
                    entry = row["close"]
                    setups.append(self._make_setup(symbol, tf, "RangeExpansion", "SHORT", session, ts,
                                                   entry, entry + atr * 1.5, entry - atr * 2.5, atr))
        return setups

    # ──────────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────────

    def _make_setup(self, symbol, tf, setup_type, direction, session, ts, entry, sl, tp, atr) -> Dict:
        return {
            "symbol": symbol, "timeframe": tf, "setup_type": setup_type,
            "direction": direction, "session": session, "timestamp": ts,
            "entry_price": round(float(entry), 6), "stop_loss": round(float(sl), 6),
            "take_profit": round(float(tp), 6), "atr": round(float(atr), 6)
        }

    def _store_setups(self, setups: List[Dict]) -> int:
        if not setups:
            return 0
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            rows = [(
                s["symbol"], s["timeframe"], s["setup_type"], s["direction"],
                s["session"], s["timestamp"], s["entry_price"], s["stop_loss"],
                s["take_profit"], s["atr"]
            ) for s in setups]
            
            cursor.executemany("""
                INSERT OR IGNORE INTO hie_setups
                (symbol, timeframe, setup_type, direction, session, timestamp, entry_price, stop_loss, take_profit, atr)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, rows)
            count = len(rows)
            conn.commit()
            return count
        except Exception as e:
            logger.error(f"SetupDetection store error: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    def get_setups(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        setup_type: Optional[str] = None,
        session: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 500
    ) -> List[Dict]:
        """Query stored setups with optional filters."""
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
            query = "SELECT * FROM hie_setups WHERE 1=1"
            params = []
            if symbol:
                query += " AND symbol=?"; params.append(symbol)
            if timeframe:
                query += " AND timeframe=?"; params.append(timeframe)
            if setup_type:
                query += " AND setup_type=?"; params.append(setup_type)
            if session:
                query += " AND session=?"; params.append(session)
            if direction:
                query += " AND direction=?"; params.append(direction)
            query += f" ORDER BY timestamp DESC LIMIT {int(limit)}"
            df = pd.read_sql_query(query, conn, params=params)
            return df.to_dict(orient="records") if not df.empty else []
        except Exception as e:
            logger.error(f"SetupDetection get_setups error: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def get_setup_count(self) -> int:
        conn = None
        try:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM hie_setups")
            n = cursor.fetchone()[0]
            return n
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()


# Singleton
setup_detection_engine = SetupDetectionEngine()
