"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 1 — HISTORICAL DATA ENGINE                                  ║
║   Downloads and maintains historical OHLCV data for all symbols      ║
║   across M1, M5, M15, H1, H4 timeframes via MT5.                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import sqlite3
import logging
import threading
import datetime as dt
from typing import Optional, List, Dict, Tuple

import pandas as pd

logger = logging.getLogger("zohra.hie.data_engine")

# Supported symbols — Strictly Gold Only (XAUUSD)
from zohra.core.symbol_resolver import symbol_resolver
HIE_SYMBOLS = ["XAUUSD"]

# Supported timeframes ordered from shortest to longest
HIE_TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4"]

# Bars per timeframe for ~2 years of data (Phase 3 lookback expansion)
BARS_PER_TF = {
    "M1":  500000,   # ~1 year of M1 (batched in chunks of 5000)
    "M5":  200000,   # ~2 years of M5
    "M15": 70000,    # ~2 years of M15
    "H1":  17000,    # ~2 years of H1
    "H4":  4500,     # ~2 years of H4
}

# Max bars per single MT5 request
MT5_MAX_BARS = 5000


# ════════════════════════════════════════════════════════════
#  HISTORICAL DATA ENGINE
# ════════════════════════════════════════════════════════════

class HistoricalDataEngine:
    """
    Downloads, stores, and serves historical OHLCV candle data.

    Data is stored in a dedicated SQLite database (hie_data.db) separate
    from the main Bot A trade database to keep isolation clean.

    Storage schema: hie_candles (symbol, timeframe, timestamp, open, high,
                                  low, close, volume, spread)
    """

    def __init__(self):
        from zohra.config.settings import settings
        db_dir = os.path.dirname(settings.DB_PATH)
        self.db_path = os.path.join(db_dir, "hie_data.db")
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._backfill_complete: Dict[str, bool] = {}  # symbol+tf → bool
        self._status = {
            "total_candles": 0,
            "symbols_loaded": 0,
            "last_update": None,
            "backfill_progress": {}
        }
        self._init_db()

    def _init_db(self):
        """Create the HIE candles table if it doesn't exist."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_candles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    timeframe   TEXT    NOT NULL,
                    timestamp   TEXT    NOT NULL,
                    open        REAL    NOT NULL,
                    high        REAL    NOT NULL,
                    low         REAL    NOT NULL,
                    close       REAL    NOT NULL,
                    volume      REAL    DEFAULT 0,
                    spread      REAL    DEFAULT 0,
                    UNIQUE(symbol, timeframe, timestamp)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hie_candles_sym_tf_ts ON hie_candles(symbol, timeframe, timestamp)")
            conn.commit()
            logger.info("✅ HIE candles table initialized.")
        except Exception as e:
            logger.error(f"HIE DB init error: {e}")
        finally:
            if conn:
                conn.close()

    # ──────────────────────────────────────────────
    #  BACKGROUND THREAD
    # ──────────────────────────────────────────────

    def start(self):
        """Start background data refresh thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-DataEngine")
        self._thread.start()
        logger.info("🏛️ HIE Historical Data Engine started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Main background loop: backfill first, then refresh every 15 minutes."""
        logger.info("📥 HIE Data Engine: Starting initial backfill loop...")
        
        while self._running:
            # Check if we have completed backfill for all symbol+tf combos
            all_complete = True
            for symbol in HIE_SYMBOLS:
                for tf in HIE_TIMEFRAMES:
                    if not self._backfill_complete.get(f"{symbol}_{tf}"):
                        all_complete = False
                        break
                if not all_complete:
                    break
            
            if not all_complete:
                from zohra.brokers.manager import broker_manager as mt5_broker
                if mt5_broker.is_connected():
                    logger.info("📥 HIE Data Engine: Running/resuming backfill...")
                    self._run_backfill()
                else:
                    logger.warning("HIE backfill pending — MT5 not connected. Retrying in 15 seconds...")
                    time.sleep(15)
                    continue
            
            # Once backfill is complete, wait 15 minutes and update incrementally
            time.sleep(900)  # 15 minutes
            self._run_incremental_update()


    def _run_backfill(self):
        """Download historical data for all symbols × timeframes."""
        from zohra.brokers.manager import broker_manager as mt5_broker
        if not mt5_broker.is_connected():
            logger.warning("HIE backfill skipped — MT5 not connected.")
            return

        for symbol in HIE_SYMBOLS:
            if not self._running:
                break
            for tf in HIE_TIMEFRAMES:
                if not self._running:
                    break
                key = f"{symbol}_{tf}"
                if self._backfill_complete.get(key):
                    continue
                try:
                    self._download_full_history(symbol, tf, mt5_broker)
                    self._backfill_complete[key] = True
                    self._status["backfill_progress"][key] = "done"
                except Exception as e:
                    logger.error(f"HIE backfill failed for {symbol}/{tf}: {e}")
                    self._status["backfill_progress"][key] = f"error: {e}"
                time.sleep(0.1)  # Rate-limit MT5 requests

        self._update_stats()
        logger.info("✅ HIE Initial backfill complete.")

    def _download_full_history(self, symbol: str, tf: str, mt5_broker):
        """Download and store all available history for symbol+tf in batches."""
        total_bars_needed = BARS_PER_TF.get(tf, 5000)
        bars_per_chunk = min(MT5_MAX_BARS, total_bars_needed)
        chunks = (total_bars_needed + bars_per_chunk - 1) // bars_per_chunk

        logger.info(f"📥 HIE: Downloading {symbol}/{tf} ({total_bars_needed} bars in {chunks} chunks)")

        stored = 0
        for chunk_idx in range(chunks):
            if not self._running:
                break
            try:
                # MT5 get_ohlcv returns most recent N bars
                # For batching, we use offset if supported; otherwise get max bars once
                df = mt5_broker.get_ohlcv(symbol, tf, count=bars_per_chunk)
                if df is None or df.empty:
                    break
                n = self._store_candles(symbol, tf, df)
                stored += n
                if chunk_idx == 0:
                    break  # Most brokers return full available history in one call
            except Exception as e:
                logger.error(f"HIE chunk download error {symbol}/{tf} chunk {chunk_idx}: {e}")
                break

        logger.info(f"✅ HIE: {symbol}/{tf} — {stored} candles stored")

    def _run_incremental_update(self):
        """Fetch latest candles to keep data current."""
        from zohra.brokers.manager import broker_manager as mt5_broker
        if not mt5_broker.is_connected():
            return
        for symbol in HIE_SYMBOLS:
            if not self._running:
                break
            for tf in ["M5", "M15", "H1", "H4"]:  # Skip M1 for incremental
                try:
                    df = mt5_broker.get_ohlcv(symbol, tf, count=50)
                    if df is not None and not df.empty:
                        self._store_candles(symbol, tf, df)
                except Exception as e:
                    logger.debug(f"HIE incremental update error {symbol}/{tf}: {e}")
        self._update_stats()

    def _store_candles(self, symbol: str, tf: str, df: pd.DataFrame) -> int:
        """Insert candles into hie_candles, ignoring duplicates. Returns count stored."""
        if df is None or df.empty:
            return 0

        # Normalize column names
        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in ("open", "high", "low", "close"):
                col_map[col] = col_lower
            elif col_lower in ("tick_volume", "real_volume", "volume"):
                col_map[col] = "volume"
            elif col_lower == "spread":
                col_map[col] = "spread"
            elif col_lower == "time":
                col_map[col] = "timestamp"
        df = df.rename(columns=col_map)
        # Deduplicate columns (e.g., if tick_volume and real_volume both got mapped to volume)
        df = df.loc[:, ~df.columns.duplicated()]


        # Ensure timestamp column exists
        if "timestamp" not in df.columns:
            if df.index.name == "time" or isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
                df = df.rename(columns={"time": "timestamp", "index": "timestamp"})
            else:
                df["timestamp"] = df.index.astype(str)

        # Convert timestamps to ISO string
        if pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S")

        df["symbol"] = symbol
        df["timeframe"] = tf

        if "volume" not in df.columns:
            df["volume"] = 0.0
        if "spread" not in df.columns:
            df["spread"] = 0.0

        required = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume", "spread"]
        df = df[[c for c in required if c in df.columns]]
        df = df.dropna(subset=["timestamp", "open"])

        rows = [tuple(row) for row in df[required].itertuples(index=False, name=None)]
        if not rows:
            return 0

        conn = None
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executemany(
                    "INSERT OR IGNORE INTO hie_candles (symbol, timeframe, timestamp, open, high, low, close, volume, spread) VALUES (?,?,?,?,?,?,?,?,?)",
                    rows
                )
                conn.commit()
            return len(rows)
        except Exception as e:
            logger.error(f"HIE store_candles DB error: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    def _update_stats(self):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM hie_candles")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT symbol) FROM hie_candles")
            syms = cursor.fetchone()[0]
            self._status["total_candles"] = total
            self._status["symbols_loaded"] = syms
            self._status["last_update"] = dt.datetime.utcnow().isoformat()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

    # ──────────────────────────────────────────────
    #  DATA ACCESS API
    # ──────────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 5000
    ) -> pd.DataFrame:
        """
        Retrieve stored historical candles as a DataFrame.

        Args:
            symbol: e.g. "EURUSD"
            timeframe: e.g. "H1"
            start: ISO timestamp string (optional)
            end: ISO timestamp string (optional)
            limit: max rows to return

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, spread
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            query = "SELECT timestamp, open, high, low, close, volume, spread FROM hie_candles WHERE symbol=? AND timeframe=?"
            params: list = [symbol, timeframe]
            if start:
                query += " AND timestamp >= ?"
                params.append(start)
            if end:
                query += " AND timestamp <= ?"
                params.append(end)
            query += f" ORDER BY timestamp ASC LIMIT {int(limit)}"
            df = pd.read_sql_query(query, conn, params=params)
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.set_index("timestamp")
            return df
        except Exception as e:
            logger.error(f"HIE get_candles error: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    def get_candles_before(self, symbol: str, timeframe: str, before_dt: str, limit: int = 500) -> pd.DataFrame:
        """
        Retrieve candles strictly before a given timestamp (for replay — no lookahead).
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            df = pd.read_sql_query(
                "SELECT timestamp, open, high, low, close, volume, spread FROM hie_candles "
                "WHERE symbol=? AND timeframe=? AND timestamp < ? "
                "ORDER BY timestamp DESC LIMIT ?",
                conn, params=[symbol, timeframe, before_dt, limit]
            )
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.sort_values("timestamp").set_index("timestamp")
            return df
        except Exception as e:
            logger.error(f"HIE get_candles_before error: {e}")
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    def get_candle_count(self, symbol: str = None, timeframe: str = None) -> int:
        """Return total stored candle count (optionally filtered)."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            cursor = conn.cursor()
            if symbol and timeframe:
                cursor.execute("SELECT COUNT(*) FROM hie_candles WHERE symbol=? AND timeframe=?", (symbol, timeframe))
            elif symbol:
                cursor.execute("SELECT COUNT(*) FROM hie_candles WHERE symbol=?", (symbol,))
            else:
                cursor.execute("SELECT COUNT(*) FROM hie_candles")
            result = cursor.fetchone()[0]
            return result
        except Exception:
            return 0
        finally:
            if conn:
                conn.close()

    def get_available_range(self, symbol: str, timeframe: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (earliest_ts, latest_ts) for a symbol+timeframe."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM hie_candles WHERE symbol=? AND timeframe=?",
                (symbol, timeframe)
            )
            row = cursor.fetchone()
            return (row[0], row[1]) if row else (None, None)
        except Exception:
            return (None, None)
        finally:
            if conn:
                conn.close()

    def get_status(self) -> dict:
        self._update_stats()
        return dict(self._status)

    @property
    def db_path_hie(self) -> str:
        return self.db_path


# Singleton
historical_data_engine = HistoricalDataEngine()
