"""
╔══════════════════════════════════════════════════════════════╗
║      MARKET ABSTRACTION LAYER — FUTURE ADAPTER TEMPLATE     ║
║  Copy this file to create a new broker adapter               ║
╚══════════════════════════════════════════════════════════════╝

INSTRUCTIONS:
  1. Copy this file to zohra/brokers/<your_broker>_adapter.py
  2. Rename the class to <YourBroker>Adapter
  3. Implement all methods marked with # TODO
  4. Register your adapter in zohra/brokers/__init__.py:
       from zohra.brokers.<your_broker>_adapter import YourBrokerAdapter
  5. Add environment variables to .env:
       YOUR_BROKER_API_KEY=...
       YOUR_BROKER_API_SECRET=...
  6. The adapter will be auto-registered when added to ACTIVE_BROKERS in .env

No changes to the Trading Core are required.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from zohra.brokers.interfaces import UnifiedBrokerAdapter
from zohra.brokers.models import (
    StandardExecution, StandardOrder, StandardTick,
    OrderSide, OrderType, ExecutionStatus,
)
from zohra.brokers.broker_logger import log_broker_call

logger = logging.getLogger("zohra.template_broker")


class TemplateBrokerAdapter(UnifiedBrokerAdapter):
    """
    Template broker adapter — copy and customize for your broker.

    Replace 'TemplateBroker' with your broker name throughout.
    Implement all methods marked with # TODO.
    """

    def __init__(self):
        self._connected = False
        # TODO: Load your broker credentials from environment
        self._api_key = os.getenv("TEMPLATE_BROKER_API_KEY", "")
        self._api_secret = os.getenv("TEMPLATE_BROKER_API_SECRET", "")
        self._session = None  # HTTP session for API calls

    # ─── Identity ──────────────────────────────────────────

    @property
    def name(self) -> str:
        """Unique broker identifier. MUST be unique across all adapters."""
        return "template"  # TODO: Change to your broker name (e.g., "zerodha", "binance")

    # ─── Connection ────────────────────────────────────────

    def connect(self) -> bool:
        """
        Establish connection to the broker API.
        Returns True on success, False on failure.

        Typical steps:
          1. Validate credentials exist
          2. Create HTTP session
          3. Make a test API call (e.g., fetch account info)
          4. Set self._connected = True
        """
        # TODO: Implement connection logic
        if not self._api_key:
            logger.error(f"{self.name}: API key not set")
            return False

        try:
            import requests
            self._session = requests.Session()
            # TODO: Set authentication headers
            # self._session.headers.update({...})

            # TODO: Make a test API call to validate credentials
            # resp = self._session.get("https://api.yourbroker.com/v1/account")
            # if resp.status_code != 200:
            #     return False

            self._connected = True
            logger.info(f"✅ {self.name} connected")
            return True

        except Exception as e:
            logger.error(f"{self.name} connection error: {e}")
            return False

    def disconnect(self) -> None:
        """Clean up connection resources."""
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False
        logger.info(f"{self.name} disconnected")

    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    # ─── Account ───────────────────────────────────────────

    @log_broker_call("get_account_info")
    def get_account_info(self) -> Optional[Dict]:
        """
        Fetch account information from the broker.

        Must return a dict with at least:
          login, server, equity, balance, margin, free_margin,
          profit, leverage, currency
        """
        # TODO: Implement API call
        return {
            "login": self._api_key[:8] + "..." if self._api_key else "",
            "server": self.name,
            "equity": 0.0,      # TODO: Fetch from API
            "balance": 0.0,     # TODO: Fetch from API
            "margin": 0.0,
            "free_margin": 0.0,
            "profit": 0.0,
            "leverage": 1,
            "currency": "USD",  # TODO: Set correct currency
        }

    def get_account_summary(self) -> Dict[str, Any]:
        info = self.get_account_info()
        if not info:
            return {}
        return {
            "balance": info["balance"],
            "equity": info["equity"],
            "margin": info["margin"],
            "free_margin": info["free_margin"],
            "currency": info["currency"],
            "login": info["login"],
            "server": info["server"],
        }

    # ─── Market Data ───────────────────────────────────────

    @log_broker_call("get_tick")
    def get_tick(self, symbol: str) -> Optional[Dict]:
        """
        Get current bid/ask for a symbol.

        Must return a dict with: bid, ask, time, spread
        """
        # TODO: Implement API call
        return None

    def get_current_price(self, symbol: str) -> Dict[str, float]:
        tick = self.get_tick(symbol)
        if not tick:
            return {}
        return {
            "bid": tick["bid"],
            "ask": tick["ask"],
            "mid": (tick["bid"] + tick["ask"]) / 2,
            "spread": tick["spread"],
        }

    # ─── Historical Data ──────────────────────────────────

    @log_broker_call("get_ohlcv")
    def get_ohlcv(self, symbol: str, timeframe: str,
                  count: int = 300) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV bars from the broker.

        Must return a DataFrame indexed by datetime with columns:
          open, high, low, close, tick_volume, real_volume

        Returns None on failure.
        """
        # TODO: Implement API call
        # 1. Map timeframe string to broker's interval format
        # 2. Make API request for candle data
        # 3. Parse response into DataFrame
        return None

    # ─── Orders ────────────────────────────────────────────

    @log_broker_call("place_order")
    def place_order(self, order: StandardOrder) -> StandardExecution:
        """
        Submit an order to the broker.

        Must construct a broker-specific order request and return
        a StandardExecution with the result.
        """
        # TODO: Implement order placement
        # 1. Convert StandardOrder to broker-specific format
        # 2. Make API call
        # 3. Parse response into StandardExecution

        return StandardExecution(
            order_id=order.order_id,
            symbol=order.symbol,
            direction=order.direction,
            status=ExecutionStatus.FAILED,
            broker=self.name,
            error="Not implemented",
        )

    def modify_order(self, order_id: str, **kwargs) -> bool:
        """Modify an existing order. Returns True on success."""
        # TODO: Implement order modification
        return False

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True on success."""
        # TODO: Implement order cancellation
        return False

    # ─── Positions ─────────────────────────────────────────

    @log_broker_call("get_positions")
    def get_positions(self, symbol: str = None, magic: int = None) -> List[Dict]:
        """
        Get open positions.

        Must return a list of dicts with at least:
          ticket, symbol, direction, lots, volume, entry_price,
          current_price, stop_loss, take_profit, profit, magic,
          comment, open_time
        """
        # TODO: Implement position query
        return []

    def get_open_positions(self, magic: int = None,
                           symbol: str = None) -> List[Dict]:
        """Alias for get_positions (backward compatibility)."""
        return self.get_positions(symbol=symbol, magic=magic)

    @log_broker_call("close_position")
    def close_position(self, ticket: int, symbol: str,
                       volume: float, direction: str) -> Dict:
        """
        Close an open position.

        Must return a dict with: success, exit_price, profit_loss
        """
        # TODO: Implement position closing
        return {"success": False, "exit_price": 0.0, "profit_loss": 0.0}

    # ─── Backward-Compatible Trade Methods ─────────────────
    # These methods match the MT5Broker API surface so the Trading
    # Core can call them without knowing the specific broker.

    def open_trade(self, symbol: str, direction: str, lots: float,
                   stop_loss: float, take_profit: float,
                   magic: int = None, comment: str = "Zohra") -> Optional[Dict]:
        side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
        order = StandardOrder(
            symbol=symbol, side=side, order_type=OrderType.MARKET,
            volume=lots, stop_loss=stop_loss, take_profit=take_profit,
            magic=magic or 0, comment=comment,
        )
        exec_result = self.place_order(order)
        if exec_result.success:
            return {
                "ticket": exec_result.ticket,
                "symbol": symbol, "direction": direction,
                "lots": lots, "price": exec_result.fill_price,
                "stop_loss": stop_loss, "take_profit": take_profit,
                "opened_at": datetime.utcnow().isoformat(),
            }
        return None

    def open_position(self, order: Dict) -> Dict:
        result = self.open_trade(
            order["symbol"], order["direction"],
            order.get("volume_lots", 0.01),
            order.get("stop_loss", 0), order.get("take_profit", 0),
        )
        if result:
            return {"success": True, "mt5_ticket": result["ticket"],
                    "fill_price": result["price"], "volume_lots": result["lots"]}
        return {"success": False, "error": f"{self.name} order failed"}

    def close_trade(self, ticket: int, symbol: str, direction: str,
                    lots: float = None, comment: str = "Close") -> Optional[Dict]:
        result = self.close_position(ticket, symbol, lots or 0.01, direction)
        if result.get("success"):
            return {"success": True, "pnl": result.get("profit_loss", 0),
                    "price": result.get("exit_price", 0), "ticket": ticket}
        return None

    def modify_trade(self, ticket: int, new_sl: float = None,
                     new_tp: float = None) -> bool:
        # TODO: Implement SL/TP modification
        return False

    def modify_stop(self, ticket: int, symbol: str,
                    stop_loss: float, take_profit: Optional[float] = None) -> Dict:
        ok = self.modify_trade(ticket, new_sl=stop_loss, new_tp=take_profit)
        return {"success": ok, "error": None if ok else "Not implemented"}

    # ─── Symbol ────────────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get metadata for a trading instrument.

        Must return a dict with: symbol, digits, point, min_lot, max_lot,
        lot_step, volume_min, volume_max, volume_step, contract, spread
        """
        # TODO: Implement symbol info lookup
        return {
            "symbol": symbol,
            "digits": 5,
            "point": 0.00001,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "contract": 100000.0,
            "spread": 0,
        }

    def is_autotrading_enabled(self) -> bool:
        """Most brokers don't have this concept — return True if connected."""
        return self._connected


# Singleton (optional — only instantiate if you want auto-registration)
# template_broker = TemplateBrokerAdapter()
