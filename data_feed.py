"""
MetaTrader 5 Data Feed Handler
Fetches candlestick data, account info, and open positions via the MT5 Python bridge.

IMPORTANT: The MetaTrader 5 desktop application must be installed, open, and
logged into your demo account before this module can connect.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict, List

from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER,
    TIMEFRAME, PAIRS
)

# ---------------------------------------------------------------------------
# MT5 timeframe map
# ---------------------------------------------------------------------------
_TIMEFRAME_MAP = {
    "M1":  1,    # mt5.TIMEFRAME_M1
    "M5":  5,    # mt5.TIMEFRAME_M5
    "M15": 15,
    "M30": 30,
    "H1":  16385,  # mt5.TIMEFRAME_H1  (actual constant value)
    "H4":  16388,
    "D1":  16408,
}

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


class MT5DataFeed:
    """
    Wraps the MetaTrader5 Python package for data and account queries.
    All public methods mirror the OandaDataFeed interface so the rest of
    the bot (scheduler, telegram, risk_manager) needs zero changes.
    """

    def __init__(self):
        self._connected = False

    # ── Connection Management ──────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Initialize MT5 and log in to the demo account.
        Must be called once at startup (done in main.py).
        Returns True on success.
        """
        if not MT5_AVAILABLE:
            print("❌ MetaTrader5 package not installed. Run: pip install MetaTrader5")
            return False

        if not mt5.initialize():
            print(f"❌ MT5 initialize() failed: {mt5.last_error()}")
            return False

        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            authorized = mt5.login(
                login=MT5_LOGIN,
                password=MT5_PASSWORD,
                server=MT5_SERVER
            )
            if not authorized:
                print(f"❌ MT5 login() failed: {mt5.last_error()}")
                mt5.shutdown()
                return False
        else:
            # Use whatever account is already logged in the terminal
            print("⚠️  MT5_LOGIN/PASSWORD/SERVER not set — using active terminal account")

        info = mt5.account_info()
        if info is None:
            print(f"❌ Cannot read account info: {mt5.last_error()}")
            mt5.shutdown()
            return False

        self._connected = True
        print(f"✅ Connected to MT5 | Account: {info.login} | "
              f"Server: {info.server} | Balance: {info.balance:.2f} {info.currency}")
        return True

    def disconnect(self):
        """Cleanly shut down the MT5 connection."""
        if MT5_AVAILABLE:
            mt5.shutdown()
        self._connected = False

    def _ensure_connected(self):
        if not self._connected:
            raise RuntimeError("MT5 not connected. Call data_feed.connect() first.")

    # ── Candle Data ────────────────────────────────────────────────────────

    def get_candles(self, instrument: str, count: int = 100,
                    granularity: str = TIMEFRAME) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles from MT5.
        Returns a DataFrame indexed by datetime with columns:
        open, high, low, close, volume
        """
        self._ensure_connected()

        tf = _TIMEFRAME_MAP.get(granularity, _TIMEFRAME_MAP["H1"])

        # Ensure the symbol is available in Market Watch
        if not mt5.symbol_select(instrument, True):
            print(f"⚠️  Symbol {instrument} not found in MT5")
            return pd.DataFrame()

        rates = mt5.copy_rates_from_pos(instrument, tf, 0, count)

        if rates is None or len(rates) == 0:
            print(f"⚠️  No candle data for {instrument}: {mt5.last_error()}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)

        # Keep only the columns we need
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.sort_index(inplace=True)

        return df

    # ── Live Price ─────────────────────────────────────────────────────────

    def get_current_price(self, instrument: str) -> Dict:
        """Get current bid/ask/mid prices for a symbol."""
        self._ensure_connected()

        tick = mt5.symbol_info_tick(instrument)
        if tick is None:
            return {}

        bid = tick.bid
        ask = tick.ask
        return {
            "bid":    bid,
            "ask":    ask,
            "mid":    (bid + ask) / 2,
            "spread": ask - bid,
        }

    # ── Account Summary ────────────────────────────────────────────────────

    def get_account_summary(self) -> Dict:
        """Get account balance, equity, margin info."""
        self._ensure_connected()

        info = mt5.account_info()
        if info is None:
            return {}

        return {
            "balance":          info.balance,
            "equity":           info.equity,
            "margin_used":      info.margin,
            "margin_available": info.margin_free,
            "open_trade_count": len(mt5.positions_get() or []),
            "currency":         info.currency,
        }

    # ── Open Positions ─────────────────────────────────────────────────────

    def get_open_positions(self) -> List[Dict]:
        """
        Get currently open positions from MT5.
        Returns a list mirroring the old OANDA format so scheduler/telegram
        need zero changes.
        """
        self._ensure_connected()

        positions = mt5.positions_get()
        if positions is None:
            return []

        result = []
        for pos in positions:
            # MT5: type 0 = BUY (LONG), type 1 = SELL (SHORT)
            direction = "LONG" if pos.type == 0 else "SHORT"
            result.append({
                "symbol":         pos.symbol,
                "direction":      direction,
                "units":          pos.volume,          # lots in MT5
                "avg_price":      pos.price_open,
                "unrealized_pnl": pos.profit,
                "ticket":         pos.ticket,          # MT5 trade ticket (replaces oanda_trade_id)
            })

        return result


# Singleton instance — connected in main.py at startup
data_feed = MT5DataFeed()
