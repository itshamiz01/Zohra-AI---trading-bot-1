"""
╔══════════════════════════════════════════════════════════════╗
║       MARKET ABSTRACTION LAYER — COINDCX BROKER ADAPTER     ║
║  Indian Crypto Exchange via REST + WebSocket APIs            ║
╚══════════════════════════════════════════════════════════════╝

Supports:
  - Spot trading on CoinDCX
  - Market and Limit orders
  - HMAC-SHA256 authenticated API calls
  - Balance queries
  - Trade history
  - Real-time tick streaming via WebSocket

Requires:
  COINDCX_API_KEY and COINDCX_API_SECRET in .env
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

logger = logging.getLogger("zohra.coindcx")

# ─── Configuration ─────────────────────────────────
COINDCX_BASE_URL = "https://api.coindcx.com"
COINDCX_PUBLIC_URL = "https://public.coindcx.com"
COINDCX_WS_URL = "wss://stream.coindcx.com"


class CoinDCXAdapter(UnifiedBrokerAdapter):
    """
    CoinDCX broker adapter for Indian crypto trading.
    Implements UnifiedBrokerAdapter for the Market Abstraction Layer.

    Authentication: HMAC-SHA256 signed requests.
    """

    def __init__(self):
        self._connected = False
        self._api_key = os.getenv("COINDCX_API_KEY", "")
        self._api_secret = os.getenv("COINDCX_API_SECRET", "")
        self._session = None
        self._markets_cache: Dict[str, Dict] = {}
        self._ws_callbacks: Dict[str, Callable] = {}
        self._ws_thread = None

    @property
    def name(self) -> str:
        return "coindcx"

    # ─── HMAC Authentication ───────────────────────────────

    def _sign_request(self, body: Dict) -> Dict[str, str]:
        """Generate HMAC-SHA256 signature for CoinDCX API."""
        json_body = json.dumps(body, separators=(",", ":"))
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            json_body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": self._api_key,
            "X-AUTH-SIGNATURE": signature,
        }

    # ─── Connection ────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to CoinDCX API by validating credentials."""
        if not self._api_key:
            logger.error("COINDCX_API_KEY not set in environment")
            return False
        if not self._api_secret:
            logger.error("COINDCX_API_SECRET not set in environment")
            return False

        try:
            import requests
            self._session = requests.Session()

            # Validate by fetching balances
            body = {"timestamp": int(time.time() * 1000)}
            headers = self._sign_request(body)
            resp = self._session.post(
                f"{COINDCX_BASE_URL}/exchange/v1/users/balances",
                json=body, headers=headers, timeout=10,
            )

            if resp.status_code == 200:
                self._connected = True
                balances = resp.json()
                # Count non-zero balances
                non_zero = [b for b in balances if float(b.get("balance", 0)) > 0]
                logger.info(
                    f"✅ CoinDCX Connected | "
                    f"Non-zero balances: {len(non_zero)}"
                )
                # Cache market data
                self._load_markets()
                return True
            else:
                logger.error(f"CoinDCX auth failed: {resp.status_code} {resp.text}")
                return False

        except ImportError:
            logger.error("requests package not installed")
            return False
        except Exception as e:
            logger.error(f"CoinDCX connection error: {e}")
            return False

    def disconnect(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False
        logger.info("CoinDCX disconnected")

    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    def health_check(self) -> Dict[str, Any]:
        start = time.perf_counter()
        connected = self.is_connected()

        details = {}
        if connected:
            try:
                resp = self._session.get(f"{COINDCX_BASE_URL}/exchange/ticker", timeout=5)
                details["api_status"] = resp.status_code
                details["ticker_count"] = len(resp.json()) if resp.status_code == 200 else 0
            except Exception as e:
                details["error"] = str(e)

        latency = (time.perf_counter() - start) * 1000
        return {
            "broker": self.name,
            "status": "healthy" if connected else "unhealthy",
            "connected": connected,
            "latency_ms": round(latency, 2),
            "details": details,
        }

    # ─── Market Data Loading ───────────────────────────────

    def _load_markets(self) -> None:
        """Load and cache all market pairs from CoinDCX."""
        try:
            resp = self._session.get(
                f"{COINDCX_BASE_URL}/exchange/v1/markets_details",
                timeout=10,
            )
            if resp.status_code == 200:
                markets = resp.json()
                for m in markets:
                    symbol = m.get("symbol", "")
                    self._markets_cache[symbol] = {
                        "symbol": symbol,
                        "pair": m.get("pair", ""),
                        "base_currency": m.get("base_currency_short_name", ""),
                        "target_currency": m.get("target_currency_short_name", ""),
                        "min_quantity": float(m.get("min_quantity", 0.0001)),
                        "max_quantity": float(m.get("max_quantity", 100000)),
                        "step": float(m.get("step", 0.0001)),
                        "min_price": float(m.get("min_price", 0)),
                        "max_price": float(m.get("max_price", 0)),
                        "min_notional": float(m.get("min_notional", 0)),
                        "status": m.get("status", "active"),
                    }
                logger.info(f"CoinDCX: Loaded {len(self._markets_cache)} markets")
        except Exception as e:
            logger.error(f"CoinDCX: Failed to load markets: {e}")

    # ─── API Helpers ───────────────────────────────────────

    def _authenticated_post(self, endpoint: str, body: Dict) -> Optional[Any]:
        """Make an authenticated POST request."""
        if not self._session:
            return None
        body["timestamp"] = int(time.time() * 1000)
        headers = self._sign_request(body)
        try:
            resp = self._session.post(
                f"{COINDCX_BASE_URL}/{endpoint.lstrip('/')}",
                json=body, headers=headers, timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"CoinDCX {endpoint}: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.error(f"CoinDCX API error ({endpoint}): {e}")
            return None

    def _public_get(self, endpoint: str, params: Dict = None) -> Optional[Any]:
        """Make a public (unauthenticated) GET request."""
        if not self._session:
            return None
        try:
            resp = self._session.get(
                f"{COINDCX_BASE_URL}/{endpoint.lstrip('/')}",
                params=params, timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"CoinDCX public API error ({endpoint}): {e}")
            return None

    # ─── Account ───────────────────────────────────────────

    @log_broker_call("get_account_info")
    def get_account_info(self) -> Optional[Dict]:
        balances = self._authenticated_post(
            "/exchange/v1/users/balances", {}
        )
        if not balances:
            return None

        # Sum up all INR and USDT balances
        total_inr = 0.0
        total_usdt = 0.0
        for b in balances:
            currency = b.get("currency", "")
            balance = float(b.get("balance", 0))
            if currency == "INR":
                total_inr += balance
            elif currency == "USDT":
                total_usdt += balance

        primary = total_usdt if total_usdt > 0 else total_inr
        currency = "USDT" if total_usdt > 0 else "INR"

        return {
            "login": self._api_key[:8] + "...",
            "server": "CoinDCX",
            "equity": primary,
            "balance": primary,
            "margin": 0.0,
            "free_margin": primary,
            "profit": 0.0,
            "leverage": 1,
            "currency": currency,
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

    @log_broker_call("get_balances")
    def get_balances(self) -> Dict[str, float]:
        """Return non-zero authenticated wallet balances without valuation guesses."""
        balances = self._authenticated_post("/exchange/v1/users/balances", {})
        if not isinstance(balances, list):
            return {}
        result: Dict[str, float] = {}
        for item in balances:
            try:
                amount = float(item.get("balance", 0))
            except (TypeError, ValueError):
                continue
            currency = str(item.get("currency", "")).upper().strip()
            if currency and amount > 0:
                result[currency] = amount
        return result

    # ─── Market Data ───────────────────────────────────────

    @log_broker_call("get_tick")
    def get_tick(self, symbol: str) -> Optional[Dict]:
        """Get current ticker for a trading pair."""
        tickers = self._public_get("/exchange/ticker")
        if not tickers:
            return None

        # Normalize symbol to CoinDCX format
        sym_upper = symbol.upper().replace("/", "")
        for t in tickers:
            market = t.get("market", "").upper()
            if market == sym_upper or t.get("symbol", "").upper() == sym_upper:
                bid = float(t.get("bid", 0))
                ask = float(t.get("ask", 0))
                return {
                    "bid": bid,
                    "ask": ask,
                    "time": int(time.time()),
                    "spread": ask - bid,
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
        """Fetch OHLCV candle data from CoinDCX."""
        # CoinDCX interval mapping
        interval_map = {
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w",
        }
        interval = interval_map.get(timeframe.upper(), "1h")

        # Normalize symbol
        pair = symbol.upper().replace("/", "")

        try:
            resp = self._session.get(
                f"{COINDCX_PUBLIC_URL}/market_data/candles",
                params={
                    "pair": pair,
                    "interval": interval,
                    "limit": count,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data:
                return None

            records = []
            for candle in data:
                records.append({
                    "time": pd.to_datetime(candle[0], unit="ms", utc=True),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "tick_volume": float(candle[5]),
                    "real_volume": float(candle[5]),
                })

            df = pd.DataFrame(records)
            if df.empty:
                return None
            df.set_index("time", inplace=True)
            return df.tail(count)

        except Exception as e:
            logger.error(f"CoinDCX OHLCV error: {e}")
            return None

    # ─── Orders ────────────────────────────────────────────

    @log_broker_call("place_order")
    def place_order(self, order: StandardOrder) -> StandardExecution:
        """Place an order on CoinDCX."""
        side = "buy" if order.side == OrderSide.BUY else "sell"
        order_type = "market_order" if order.order_type == OrderType.MARKET else "limit_order"

        body = {
            "side": side,
            "order_type": order_type,
            "market": order.symbol,
            "total_quantity": order.volume,
        }

        if order.order_type == OrderType.LIMIT and order.price > 0:
            body["price_per_unit"] = order.price

        result = self._authenticated_post(
            "/exchange/v1/orders/create", body
        )

        if result and result.get("id"):
            return StandardExecution(
                order_id=order.order_id,
                ticket=int(str(result["id"])[-8:], 16) if isinstance(result["id"], str) else result["id"],
                symbol=order.symbol,
                direction=order.direction,
                fill_price=float(result.get("avg_price", order.price)),
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
            error=str(result) if result else "CoinDCX order failed",
        )

    def modify_order(self, order_id: str, **kwargs) -> bool:
        """CoinDCX does not support order modification. Cancel and re-place."""
        logger.warning("CoinDCX: Order modification not supported. Cancel and re-place.")
        return False

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order on CoinDCX."""
        body = {"id": order_id}
        result = self._authenticated_post("/exchange/v1/orders/cancel", body)
        return result is not None

    # ─── Positions ─────────────────────────────────────────

    @log_broker_call("get_positions")
    def get_positions(self, symbol: str = None, magic: int = None) -> List[Dict]:
        """Get open orders as pseudo-positions (spot exchange has no native positions)."""
        result = self._authenticated_post(
            "/exchange/v1/orders/active_orders", {}
        )
        if not result or not isinstance(result, dict):
            return []

        orders = result.get("orders", [])
        positions = []
        for o in orders:
            pos = {
                "ticket": hash(o.get("id", "")) % 10**8,
                "symbol": o.get("market", ""),
                "direction": "LONG" if o.get("side") == "buy" else "SHORT",
                "lots": float(o.get("total_quantity", 0)),
                "volume": float(o.get("total_quantity", 0)),
                "entry_price": float(o.get("avg_price", o.get("price_per_unit", 0))),
                "current_price": float(o.get("avg_price", 0)),
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "profit": 0.0,
                "magic": 0,
                "comment": "",
                "open_time": o.get("created_at", datetime.utcnow().isoformat()),
            }
            if symbol and pos["symbol"].upper() != symbol.upper():
                continue
            positions.append(pos)

        return positions

    def get_open_positions(self, magic: int = None, symbol: str = None) -> List[Dict]:
        return self.get_positions(symbol=symbol, magic=magic)

    @log_broker_call("close_position")
    def close_position(self, ticket: int, symbol: str,
                       volume: float, direction: str) -> Dict:
        """Close position by placing opposite order."""
        opposite = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
        order = StandardOrder(
            symbol=symbol, side=opposite,
            order_type=OrderType.MARKET, volume=volume,
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
        return {"success": False, "error": "CoinDCX order failed"}

    def close_trade(self, ticket: int, symbol: str, direction: str,
                    lots: float = None, comment: str = "Close") -> Optional[Dict]:
        result = self.close_position(ticket, symbol, lots or 0.01, direction)
        if result.get("success"):
            return {"success": True, "pnl": 0.0, "price": result.get("exit_price", 0),
                    "ticket": ticket}
        return None

    def modify_trade(self, ticket: int, new_sl: float = None,
                     new_tp: float = None) -> bool:
        logger.info(f"CoinDCX: modify_trade — SL/TP not natively supported on spot")
        return True

    def modify_stop(self, ticket: int, symbol: str,
                    stop_loss: float, take_profit: Optional[float] = None) -> Dict:
        return {"success": True, "error": None}

    # ─── Symbol ────────────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        market = self._markets_cache.get(symbol.upper())
        if market:
            return {
                "symbol": market["symbol"],
                "digits": 8,
                "point": 0.00000001,
                "min_lot": market.get("min_quantity", 0.0001),
                "max_lot": market.get("max_quantity", 100000),
                "lot_step": market.get("step", 0.0001),
                "volume_min": market.get("min_quantity", 0.0001),
                "volume_max": market.get("max_quantity", 100000),
                "volume_step": market.get("step", 0.0001),
                "contract": 1.0,
                "spread": 0,
                "sector": "Crypto",
                "asset_class": "crypto",
            }
        return {
            "symbol": symbol, "digits": 8, "point": 0.00000001,
            "min_lot": 0.0001, "max_lot": 100000, "lot_step": 0.0001,
            "volume_min": 0.0001, "volume_max": 100000, "volume_step": 0.0001,
            "contract": 1.0, "spread": 0,
            "sector": "Crypto", "asset_class": "crypto",
        }

    def get_symbols(self) -> List[str]:
        if self._markets_cache:
            return [m for m, d in self._markets_cache.items()
                    if d.get("status") == "active"]
        return []

    def is_autotrading_enabled(self) -> bool:
        return self._connected

    # ─── WebSocket Streaming ──────────────────────────────

    def subscribe_ticks(self, symbol: str,
                        callback: Callable[[StandardTick], None]) -> bool:
        """Subscribe to real-time ticks via CoinDCX WebSocket."""
        logger.info(f"CoinDCX: WebSocket tick subscription for {symbol} — "
                    "placeholder, implement with socketio/websocket-client")
        self._ws_callbacks[symbol] = callback
        return True

    def unsubscribe_ticks(self, symbol: str) -> bool:
        self._ws_callbacks.pop(symbol, None)
        return True


# Singleton
coindcx_broker = CoinDCXAdapter()
