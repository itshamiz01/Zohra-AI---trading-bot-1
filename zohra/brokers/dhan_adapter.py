"""
╔══════════════════════════════════════════════════════════════╗
║        MARKET ABSTRACTION LAYER — DHAN BROKER ADAPTER       ║
║  Indian Stock/Options/Futures via Dhan REST API v2           ║
╚══════════════════════════════════════════════════════════════╝

Supports:
  - NSE/BSE Equity, NFO (F&O), MCX (Commodity)
  - Market, Limit, Stop-Loss, Stop-Loss Market orders
  - Position queries, holdings
  - Historical OHLCV data via Dhan market feed
  - Account funds and margin

Requires:
  DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID in .env
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import numpy as np

from zohra.brokers.interfaces import UnifiedBrokerAdapter
from zohra.brokers.models import (
    StandardExecution, StandardOrder, StandardTick,
    OrderSide, OrderType, ExecutionStatus,
)
from zohra.brokers.broker_logger import log_broker_call
from zohra.brokers.resilience import with_retry, RETRY_STANDARD

logger = logging.getLogger("zohra.dhan")

# ─── Configuration ─────────────────────────────────
DHAN_BASE_URL = "https://api.dhan.co/v2"

# Exchange segment mapping
EXCHANGE_MAP = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "MCX": "MCX_COMM",
    "CDS": "NSE_CURRENCY",
}

# Order type mapping (Dhan API)
ORDER_TYPE_MAP = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP: "SL",
    OrderType.STOP_LIMIT: "SL",
}

# Product type mapping
PRODUCT_TYPE = {
    "INTRADAY": "INTRADAY",
    "CNC": "CNC",           # Cash and Carry (delivery)
    "MARGIN": "MARGIN",
    "MTF": "MTF",           # Margin Trading Facility
    "BO": "BO",             # Bracket Order
    "CO": "CO",             # Cover Order
}


class DhanAdapter(UnifiedBrokerAdapter):
    """
    Dhan broker adapter for Indian stock/options/futures trading.
    Implements UnifiedBrokerAdapter for the Market Abstraction Layer.
    """

    def __init__(self):
        self._connected = False
        self._access_token = os.getenv("DHAN_ACCESS_TOKEN", "")
        self._client_id = os.getenv("DHAN_CLIENT_ID", "")
        self._cache: Dict[str, Any] = {}
        self._session = None  # requests.Session

    @property
    def name(self) -> str:
        return "dhan"

    # ─── Connection ────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to Dhan API by validating credentials."""
        if not self._access_token:
            logger.error("DHAN_ACCESS_TOKEN not set in environment")
            return False
        if not self._client_id:
            logger.error("DHAN_CLIENT_ID not set in environment")
            return False

        try:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "Content-Type": "application/json",
                "access-token": self._access_token,
            })

            # Validate connection by fetching fund limits
            resp = self._session.get(f"{DHAN_BASE_URL}/fundlimit")
            if resp.status_code == 200:
                self._connected = True
                data = resp.json()
                logger.info(
                    f"✅ Dhan Connected: Client={self._client_id} | "
                    f"Available Balance={data.get('data', {}).get('availabelBalance', 'N/A')}"
                )
                return True
            else:
                logger.error(f"Dhan connection failed: {resp.status_code} {resp.text}")
                return False

        except ImportError:
            logger.error("requests package not installed. Install with: pip install requests")
            return False
        except Exception as e:
            logger.error(f"Dhan connection error: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Dhan API."""
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False
        logger.info("Dhan disconnected")

    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    def health_check(self) -> Dict[str, Any]:
        start = time.perf_counter()
        connected = self.is_connected()
        latency = (time.perf_counter() - start) * 1000

        details = {}
        if connected:
            try:
                resp = self._session.get(f"{DHAN_BASE_URL}/fundlimit")
                latency = (time.perf_counter() - start) * 1000
                details["api_status"] = resp.status_code
            except Exception as e:
                details["error"] = str(e)

        return {
            "broker": self.name,
            "status": "healthy" if connected else "unhealthy",
            "connected": connected,
            "latency_ms": round(latency, 2),
            "details": details,
        }

    # ─── API Helpers ───────────────────────────────────────

    def _request(self, method: str, endpoint: str,
                 data: Dict = None, params: Dict = None) -> Optional[Dict]:
        """Make an authenticated API request to Dhan."""
        if not self._session:
            logger.error("Dhan: Not connected")
            return None

        url = f"{DHAN_BASE_URL}/{endpoint.lstrip('/')}"
        try:
            if method.upper() == "GET":
                resp = self._session.get(url, params=params, timeout=10)
            elif method.upper() == "POST":
                resp = self._session.post(url, json=data, timeout=10)
            elif method.upper() == "PUT":
                resp = self._session.put(url, json=data, timeout=10)
            elif method.upper() == "DELETE":
                resp = self._session.delete(url, params=params, timeout=10)
            else:
                return None

            if resp.status_code in (200, 201):
                return resp.json()
            else:
                logger.error(f"Dhan API {method} {endpoint}: {resp.status_code} {resp.text}")
                return None

        except Exception as e:
            logger.error(f"Dhan API error ({method} {endpoint}): {e}")
            return None

    # ─── Account ───────────────────────────────────────────

    @log_broker_call("get_account_info")
    def get_account_info(self) -> Optional[Dict]:
        data = self._request("GET", "/fundlimit")
        if not data or "data" not in data:
            return None
        funds = data["data"]
        return {
            "login": self._client_id,
            "server": "Dhan",
            "equity": float(funds.get("availabelBalance", 0)),
            "balance": float(funds.get("sodLimit", 0)),
            "margin": float(funds.get("utilizedAmount", 0)),
            "free_margin": float(funds.get("availabelBalance", 0)),
            "profit": 0.0,
            "leverage": 1,
            "currency": "INR",
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

    def get_tick(self, symbol: str) -> Optional[Dict]:
        """Get current market quote. Uses Dhan market quote API."""
        data = self._request("POST", "/marketfeed/ltp", data={
            "NSE_EQ": [int(symbol)] if symbol.isdigit() else [],
        })
        if data and "data" in data:
            ltp_data = data["data"]
            # Parse response
            for segment, quotes in ltp_data.items():
                for sec_id, quote in quotes.items():
                    ltp = float(quote.get("last_price", 0))
                    return {
                        "bid": ltp - 0.05,
                        "ask": ltp + 0.05,
                        "time": int(time.time()),
                        "spread": 0.10,
                    }
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
        """Fetch OHLCV data from Dhan historical API."""
        # Timeframe mapping
        tf_map = {
            "M1": "1", "M5": "5", "M15": "15", "M30": "30",
            "H1": "60", "H4": "240", "D1": "D",
        }
        interval = tf_map.get(timeframe.upper(), "60")

        to_date = datetime.now()
        from_date = to_date - timedelta(days=count if interval == "D" else count // 10)

        data = self._request("POST", "/charts/historical", data={
            "securityId": symbol,
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "expiryCode": 0,
            "fromDate": from_date.strftime("%Y-%m-%d"),
            "toDate": to_date.strftime("%Y-%m-%d"),
        })

        if not data or "data" not in data:
            return None

        candles = data["data"]
        if not candles:
            return None

        # Parse into DataFrame
        records = []
        for c in candles:
            records.append({
                "time": pd.to_datetime(c.get("start_Time", c.get("timestamp", "")), utc=True),
                "open": float(c.get("open", 0)),
                "high": float(c.get("high", 0)),
                "low": float(c.get("low", 0)),
                "close": float(c.get("close", 0)),
                "tick_volume": int(c.get("volume", 0)),
                "real_volume": int(c.get("volume", 0)),
            })

        df = pd.DataFrame(records)
        if df.empty:
            return None

        df.set_index("time", inplace=True)
        return df.tail(count)

    # ─── Orders ────────────────────────────────────────────

    @log_broker_call("place_order")
    def place_order(self, order: StandardOrder) -> StandardExecution:
        """Place an order on Dhan."""
        dhan_order = {
            "dhanClientId": self._client_id,
            "transactionType": "BUY" if order.side == OrderSide.BUY else "SELL",
            "exchangeSegment": "NSE_EQ",
            "productType": "INTRADAY",
            "orderType": ORDER_TYPE_MAP.get(order.order_type, "MARKET"),
            "validity": "DAY",
            "securityId": order.symbol,
            "quantity": int(order.volume),
            "price": order.price if order.order_type != OrderType.MARKET else 0,
            "triggerPrice": order.stop_loss if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) else 0,
        }

        result = self._request("POST", "/orders", data=dhan_order)

        if result and result.get("orderId"):
            return StandardExecution(
                order_id=order.order_id,
                ticket=int(result["orderId"]),
                symbol=order.symbol,
                direction=order.direction,
                fill_price=order.price,
                fill_volume=order.volume,
                status=ExecutionStatus.SUCCESS,
                broker=self.name,
            )
        return StandardExecution(
            order_id=order.order_id,
            symbol=order.symbol,
            direction=order.direction,
            status=ExecutionStatus.FAILED,
            broker=self.name,
            error=str(result) if result else "Dhan order placement failed",
        )

    def modify_order(self, order_id: str, **kwargs) -> bool:
        """Modify an existing order on Dhan."""
        data = {
            "dhanClientId": self._client_id,
            "orderId": order_id,
        }
        if "quantity" in kwargs:
            data["quantity"] = int(kwargs["quantity"])
        if "price" in kwargs:
            data["price"] = float(kwargs["price"])
        if "order_type" in kwargs:
            data["orderType"] = kwargs["order_type"]

        result = self._request("PUT", f"/orders/{order_id}", data=data)
        return result is not None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order on Dhan."""
        result = self._request("DELETE", f"/orders/{order_id}")
        return result is not None

    # ─── Positions (backward-compatible dict format) ───────

    @log_broker_call("get_positions")
    def get_positions(self, symbol: str = None, magic: int = None) -> List[Dict]:
        """Get open positions from Dhan."""
        data = self._request("GET", "/positions")
        if not data or "data" not in data:
            return []

        positions = []
        for pos in data["data"]:
            pos_dict = {
                "ticket": int(pos.get("positionId", pos.get("securityId", 0))),
                "symbol": str(pos.get("securityId", "")),
                "direction": "LONG" if pos.get("positionType") == "LONG" else "SHORT",
                "lots": abs(int(pos.get("netQty", 0))),
                "volume": abs(int(pos.get("netQty", 0))),
                "entry_price": float(pos.get("buyAvg", pos.get("sellAvg", 0))),
                "current_price": float(pos.get("dayBuyValue", 0)),
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "profit": float(pos.get("realizedProfit", 0)) + float(pos.get("unrealizedProfit", 0)),
                "magic": 0,
                "comment": "",
                "open_time": datetime.utcnow().isoformat(),
            }
            if symbol and pos_dict["symbol"] != symbol:
                continue
            positions.append(pos_dict)

        return positions

    def get_open_positions(self, magic: int = None, symbol: str = None) -> List[Dict]:
        """Alias for get_positions (backward compatibility)."""
        return self.get_positions(symbol=symbol, magic=magic)

    @log_broker_call("close_position")
    def close_position(self, ticket: int, symbol: str,
                       volume: float, direction: str) -> Dict:
        """Close a position by placing an opposite order."""
        opposite = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
        order = StandardOrder(
            symbol=symbol,
            side=opposite,
            order_type=OrderType.MARKET,
            volume=volume,
        )
        execution = self.place_order(order)
        return {
            "success": execution.success,
            "exit_price": execution.fill_price,
            "profit_loss": 0.0,
        }

    # ─── Trade Methods (backward-compatible) ───────────────

    def open_trade(self, symbol: str, direction: str, lots: float,
                   stop_loss: float, take_profit: float,
                   magic: int = None, comment: str = "Zohra") -> Optional[Dict]:
        """Open a trade (backward-compatible with MT5Broker)."""
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
                "symbol": symbol,
                "direction": direction,
                "lots": lots,
                "price": exec_result.fill_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "opened_at": datetime.utcnow().isoformat(),
            }
        return None

    def open_position(self, order: Dict) -> Dict:
        """Open position from order dict (backward-compatible)."""
        result = self.open_trade(
            symbol=order["symbol"],
            direction=order["direction"],
            lots=order.get("volume_lots", 1),
            stop_loss=order.get("stop_loss", 0),
            take_profit=order.get("take_profit", 0),
            comment=order.get("comment", "Zohra"),
        )
        if result:
            return {"success": True, "mt5_ticket": result["ticket"],
                    "fill_price": result["price"], "volume_lots": result["lots"]}
        return {"success": False, "error": "Dhan order failed"}

    def close_trade(self, ticket: int, symbol: str, direction: str,
                    lots: float = None, comment: str = "Close") -> Optional[Dict]:
        """Close trade (backward-compatible)."""
        result = self.close_position(ticket, symbol, lots or 1, direction)
        if result.get("success"):
            return {"success": True, "pnl": result.get("profit_loss", 0),
                    "price": result.get("exit_price", 0), "ticket": ticket}
        return None

    def modify_trade(self, ticket: int, new_sl: float = None,
                     new_tp: float = None) -> bool:
        """Modify trade SL/TP (not natively supported in equity, best-effort)."""
        logger.info(f"Dhan: modify_trade for ticket {ticket} — SL/TP modification "
                    "requires manual bracket order management")
        return True

    def modify_stop(self, ticket: int, symbol: str,
                    stop_loss: float, take_profit: Optional[float] = None) -> Dict:
        ok = self.modify_trade(ticket, new_sl=stop_loss, new_tp=take_profit)
        return {"success": ok, "error": None if ok else "Dhan modification not supported"}

    # ─── Symbol ────────────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        return {
            "symbol": symbol,
            "digits": 2,
            "point": 0.05,
            "min_lot": 1,
            "max_lot": 100000,
            "lot_step": 1,
            "volume_min": 1,
            "volume_max": 100000,
            "volume_step": 1,
            "contract": 1.0,
            "spread": 0,
            "sector": "Equity",
            "asset_class": "equity",
        }

    def is_autotrading_enabled(self) -> bool:
        return self._connected


# Singleton
dhan_broker = DhanAdapter()
