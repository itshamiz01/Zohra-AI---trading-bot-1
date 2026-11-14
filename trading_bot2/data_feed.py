"""
MT5 Data Feed Handler
Fetches candlestick data and account info via MetaTrader 5.
"""

import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, TIMEFRAME


class MT5DataFeed:
    """
    MT5 data feed — replaces all OANDA REST calls.
    All public methods mirror the original interface so the rest of
    the codebase (scheduler, telegram, strategy) works unchanged.
    """

    TF_MAP = {
        "M1":  1,   "M5":  5,   "M15": 15,  "M30": 30,
        "H1":  16385, "H4": 16388, "D1": 16408, "W1": 32769,
    }

    def __init__(self):
        self._connected = False

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            print("[DataFeed] MetaTrader5 not installed.")
            return False
        if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            print(f"[DataFeed] MT5 init failed: {mt5.last_error()}")
            return False
        self._connected = True
        return True

    def _tf(self, granularity: str = None):
        """Convert timeframe string to MT5 constant."""
        tf_str = (granularity or TIMEFRAME).upper()
        TF_CONSTS = {
            "M1":  mt5.TIMEFRAME_M1  if MT5_AVAILABLE else 1,
            "M5":  mt5.TIMEFRAME_M5  if MT5_AVAILABLE else 5,
            "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
            "M30": mt5.TIMEFRAME_M30 if MT5_AVAILABLE else 30,
            "H1":  mt5.TIMEFRAME_H1  if MT5_AVAILABLE else 16385,
            "H4":  mt5.TIMEFRAME_H4  if MT5_AVAILABLE else 16388,
            "D1":  mt5.TIMEFRAME_D1  if MT5_AVAILABLE else 16408,
        }
        return TF_CONSTS.get(tf_str, mt5.TIMEFRAME_H1 if MT5_AVAILABLE else 16385)

    def get_candles(self, instrument: str, count: int = 100,
                    granularity: str = None) -> pd.DataFrame:
        """
        Fetch historical OHLCV bars from MT5.
        Returns DataFrame with columns: open, high, low, close, volume.
        """
        if not MT5_AVAILABLE:
            return pd.DataFrame()

        if not mt5.symbol_select(instrument, True):
            return pd.DataFrame()

        rates = mt5.copy_rates_from_pos(instrument, self._tf(granularity), 0, count)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('time', inplace=True)
        df.rename(columns={
            'tick_volume': 'volume',
            'real_volume': 'real_volume',
        }, inplace=True)

        # Keep only complete candles (drop latest open bar)
        return df.iloc[:-1]

    def get_current_price(self, instrument: str) -> Dict:
        """Get current bid/ask prices from MT5 tick."""
        if not MT5_AVAILABLE:
            return {}
        tick = mt5.symbol_info_tick(instrument)
        if tick is None:
            return {}
        mid = (tick.bid + tick.ask) / 2
        return {
            "bid":    tick.bid,
            "ask":    tick.ask,
            "mid":    mid,
            "spread": tick.ask - tick.bid,
        }

    def get_account_summary(self) -> Dict:
        """Get MT5 account balance, equity, margin."""
        if not MT5_AVAILABLE:
            return {}
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            "balance":           info.balance,
            "equity":            info.equity,
            "margin_used":       info.margin,
            "margin_available":  info.margin_free,
            "open_trade_count":  len(mt5.positions_get() or []),
            "currency":          info.currency,
            "leverage":          info.leverage,
        }

    def get_open_positions(self) -> List[Dict]:
        """
        Returns a list mirroring the original interface so scheduler/telegram
        work unchanged. Uses MT5 positions_get().
        """
        if not MT5_AVAILABLE:
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        result = []
        for pos in positions:
            result.append({
                "symbol":          pos.symbol,
                "direction":       "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT",
                "lots":            pos.volume,
                "avg_price":       pos.price_open,
                "unrealized_pnl":  pos.profit,
                "ticket":         pos.ticket,          # MT5 trade ticket (replaces oanda_trade_id)
                "mt5_ticket":     pos.ticket,
                "stop_loss":      pos.sl,
                "take_profit":    pos.tp,
            })
        return result


# Singleton instance
data_feed = MT5DataFeed()
