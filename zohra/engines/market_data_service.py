"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — CENTRALIZED MARKET DATA SERVICE                    ║
║     Single point of market data ingestion, caching & distribution   ║
╚══════════════════════════════════════════════════════════════════════╝

This process owns all market-data ingestion:
  - Tick data (bid/ask/spread)
  - OHLCV candles across all timeframes
  - Symbol metadata
  - Market sessions / market status
  - Data caching (prevents N strategies from independently hammering MT5)

Data flow:
  MT5 / Broker → Market Data Service → Normalized Market Data → Strategy Engine
"""

import os
import sys
import time
import logging
import asyncio
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from zohra.core.message_bus import message_bus, ZohraMessage, MessageTopic
from zohra.config.settings import (
    ACTIVE_PAIRS, SCAN_INTERVAL_SEC,
    TF_H4, TF_H1, TF_M15, TF_M5,
)

logger = logging.getLogger("zohra.market_data_service")


class MarketDataService:
    """
    Centralized Market Data Service for the ZOHRA unified trading system.

    Responsibilities:
    - Owns a single MT5 connection for market data (read-only, no trade execution)
    - Fetches tick data, OHLCV candles for all symbols and timeframes
    - Caches data to prevent redundant MT5 API calls
    - Publishes normalized market.data and market.tick messages
    - Monitors market sessions and market status

    This process should NEVER:
    - Place orders
    - Modify positions
    - Access account-specific information
    - Login to trading accounts
    """

    PROCESS_NAME = "zohra-market-data"
    TIMEFRAMES = [TF_H4, TF_H1, TF_M15, TF_M5]
    TICK_INTERVAL_SEC = 5.0     # Poll ticks every 5 seconds
    OHLC_INTERVAL_SEC = 15.0    # Poll OHLC every 15 seconds

    def __init__(self, symbols: List[str] = None):
        self.symbols = symbols or list(ACTIVE_PAIRS)
        self._running = False
        self._start_time = 0.0

        # ─── Data Cache ───
        self._ohlc_cache: Dict[str, Dict[str, pd.DataFrame]] = {}  # {symbol: {tf: df}}
        self._tick_cache: Dict[str, Dict[str, Any]] = {}            # {symbol: tick_data}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_lock = threading.Lock()

        # ─── MT5 Broker (read-only) ───
        self._broker = None

        logger.info(f"MarketDataService initialized | Symbols: {self.symbols} | Timeframes: {self.TIMEFRAMES}")

    # ═══════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═══════════════════════════════════════════════════════════

    def start(self) -> bool:
        """Initialize MT5 connection and start data polling."""
        from zohra.brokers.mt5_broker import MT5Broker
        self._broker = MT5Broker()

        if not self._broker.connect():
            logger.error("MarketDataService: Failed to connect to MT5 for market data.")
            return False

        self._running = True
        self._start_time = time.time()
        logger.info("✅ MarketDataService started — polling market data")
        return True

    def stop(self):
        """Stop data polling and disconnect."""
        self._running = False
        if self._broker:
            self._broker.disconnect()
        logger.info("MarketDataService stopped")

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    # ═══════════════════════════════════════════════════════════
    #  DATA POLLING LOOP
    # ═══════════════════════════════════════════════════════════

    async def run_loop(self):
        """Main async data polling loop."""
        last_ohlc_poll = 0.0
        last_tick_poll = 0.0

        while self._running:
            try:
                now = time.time()

                # ─── Tick Polling ───
                if now - last_tick_poll >= self.TICK_INTERVAL_SEC:
                    await self._poll_ticks()
                    last_tick_poll = now

                # ─── OHLC Polling ───
                if now - last_ohlc_poll >= self.OHLC_INTERVAL_SEC:
                    await self._poll_ohlc()
                    last_ohlc_poll = now

                # ─── Heartbeat ───
                await message_bus.publish_heartbeat(
                    self.PROCESS_NAME, "HEALTHY", self.uptime
                )

                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"MarketDataService loop error: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    # ═══════════════════════════════════════════════════════════
    #  TICK DATA
    # ═══════════════════════════════════════════════════════════

    async def _poll_ticks(self):
        """Fetch latest tick for all symbols and publish to bus."""
        for symbol in self.symbols:
            try:
                tick = self._broker.get_tick(symbol)
                if tick is None:
                    continue

                with self._cache_lock:
                    self._tick_cache[symbol] = tick

                await message_bus.publish_market_tick(
                    symbol=symbol,
                    bid=tick["bid"],
                    ask=tick["ask"],
                    spread=tick["spread"],
                    source=self.PROCESS_NAME,
                )

            except Exception as e:
                logger.warning(f"Tick poll error for {symbol}: {e}")

    # ═══════════════════════════════════════════════════════════
    #  OHLCV DATA
    # ═══════════════════════════════════════════════════════════

    async def _poll_ohlc(self):
        """Fetch OHLCV data for all symbols/timeframes and publish to bus."""
        for symbol in self.symbols:
            for tf in self.TIMEFRAMES:
                try:
                    cache_key = f"{symbol}_{tf}"

                    df = self._broker.get_ohlcv(symbol, tf, count=300)
                    if df is None or len(df) < 10:
                        continue

                    with self._cache_lock:
                        if symbol not in self._ohlc_cache:
                            self._ohlc_cache[symbol] = {}
                        self._ohlc_cache[symbol][tf] = df
                        self._cache_timestamps[cache_key] = time.time()

                    # Publish the latest candle data as a message
                    latest = df.iloc[-1]
                    await message_bus.publish_market_data(
                        symbol=symbol,
                        timeframe=tf,
                        data={
                            "open": float(latest["open"]),
                            "high": float(latest["high"]),
                            "low": float(latest["low"]),
                            "close": float(latest["close"]),
                            "tick_volume": int(latest.get("tick_volume", 0)),
                            "candle_count": len(df),
                            "timestamp": str(df.index[-1]) if hasattr(df.index[-1], 'isoformat') else str(df.index[-1]),
                        },
                        source=self.PROCESS_NAME,
                    )

                except Exception as e:
                    logger.warning(f"OHLC poll error for {symbol}/{tf}: {e}")

    # ═══════════════════════════════════════════════════════════
    #  CACHED DATA ACCESS (for in-process consumers)
    # ═══════════════════════════════════════════════════════════

    def get_cached_ohlc(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Get cached OHLCV DataFrame (used by strategy engine in same process)."""
        with self._cache_lock:
            return self._ohlc_cache.get(symbol, {}).get(timeframe)

    def get_cached_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached tick data."""
        with self._cache_lock:
            return self._tick_cache.get(symbol)

    def get_cached_multi_tf(self, symbol: str, timeframes: List[str] = None) -> Dict[str, Optional[pd.DataFrame]]:
        """Get cached data across multiple timeframes for a symbol."""
        tfs = timeframes or self.TIMEFRAMES
        with self._cache_lock:
            sym_data = self._ohlc_cache.get(symbol, {})
            return {tf: sym_data.get(tf) for tf in tfs}

    def get_spread_pips(self, symbol: str) -> float:
        """Get cached spread in pips."""
        tick = self.get_cached_tick(symbol)
        if not tick:
            return 999.0
        spread = tick.get("spread", 0)
        if "JPY" in symbol:
            return spread * 100
        elif "XAU" in symbol:
            return spread * 10
        else:
            return spread * 10_000

    def is_market_open(self) -> bool:
        """Check if market is open based on cached data freshness."""
        if not self._tick_cache:
            return False
        # If we have recent tick data (< 30s old), market is open
        for symbol in self.symbols:
            cache_key = f"{symbol}_{TF_M5}"
            ts = self._cache_timestamps.get(cache_key, 0)
            if time.time() - ts < 30:
                return True
        return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._cache_lock:
            return {
                "symbols_cached": list(self._ohlc_cache.keys()),
                "ticks_cached": list(self._tick_cache.keys()),
                "cache_entries": len(self._cache_timestamps),
            }
