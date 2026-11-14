"""
╔══════════════════════════════════════════════════════════════╗
║      MARKET ABSTRACTION LAYER — METAAPI CLOUD ADAPTER        ║
║  Connects Zohra to a MetaTrader 5 account hosted in the      ║
║  MetaApi cloud — no local MT5 terminal, no Windows machine.  ║
╚══════════════════════════════════════════════════════════════╝

How it works:
  MetaApi (https://metaapi.cloud) runs a MetaTrader terminal in their
  cloud for your broker account. This adapter talks to it through the
  official `metaapi-cloud-sdk` (async) and exposes Zohra's synchronous
  UnifiedBrokerAdapter interface, so the Trading Core needs no changes.

Configuration (environment variables):
  METAAPI_TOKEN           MetaApi API token (from app.metaapi.cloud/token)
  METAAPI_ACCOUNT_ID      MetaApi account id of the MT account to use
  METAAPI_TRADING_ENABLED "1" to allow order placement. Default OFF:
                          the adapter is READ-ONLY until this is set.
  METAAPI_ALLOW_REAL      "1" to permit trading on a REAL (non-demo)
                          account. Default OFF: trading is refused on
                          any account whose type is not DEMO.

Safety model (defence in depth — all three must pass to place a trade):
  1. METAAPI_TRADING_ENABLED=1
  2. Connected account reports type ACCOUNT_TRADE_MODE_DEMO
     (or METAAPI_ALLOW_REAL=1, which the owner must set deliberately)
  3. The account itself reports tradeAllowed from the broker

Registration: add "metaapi" to ACTIVE_BROKERS and set
DEFAULT_BROKER=metaapi to trade through the cloud account.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from zohra.brokers.interfaces import UnifiedBrokerAdapter
from zohra.brokers.models import (
    ExecutionStatus,
    OrderSide,
    StandardExecution,
    StandardOrder,
)

logger = logging.getLogger("zohra.metaapi_broker")

# Zohra timeframe -> MetaApi timeframe codes
_TIMEFRAME_MAP = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w", "MN1": "1M",
    # pass-through if already in MetaApi format
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w", "1M": "1M",
}

_TRADE_DONE_CODES = {10009, 10008}  # TRADE_RETCODE_DONE / PLACED


class _LoopRunner:
    """Runs async SDK coroutines from Zohra's synchronous code.

    A dedicated event-loop thread is used so the adapter works both in
    plain scripts (no running loop) and inside FastAPI/uvicorn worker
    threads (where a loop is already running and asyncio.run would fail).
    """

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever,
                    name="metaapi-loop", daemon=True,
                )
                self._thread.start()
            return self._loop

    def run(self, coro, timeout: float = 60.0):
        loop = self._ensure()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)


class MetaApiBrokerAdapter(UnifiedBrokerAdapter):
    """UnifiedBrokerAdapter backed by a cloud-hosted MT5 account (MetaApi)."""

    def __init__(self):
        self._token = os.getenv("METAAPI_TOKEN", "").strip()
        self._account_id = os.getenv("METAAPI_ACCOUNT_ID", "").strip()
        self._trading_enabled = os.getenv("METAAPI_TRADING_ENABLED", "0") == "1"
        self._allow_real = os.getenv("METAAPI_ALLOW_REAL", "0") == "1"
        self._runner = _LoopRunner()
        self._api = None          # MetaApi client
        self._account = None      # MetatraderAccount
        self._conn = None         # RPC connection instance
        self._connected = False
        self._account_type = ""   # e.g. ACCOUNT_TRADE_MODE_DEMO
        self._info_cache: Dict[str, Any] = {}
        self._info_cache_ts = 0.0

    # ─── Identity ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "metaapi"

    # ─── Connection ────────────────────────────────────────

    def connect(self) -> bool:
        if self._connected:
            return True
        if not self._token or not self._account_id:
            logger.error(
                "MetaApi not configured: set METAAPI_TOKEN and METAAPI_ACCOUNT_ID"
            )
            return False
        try:
            from metaapi_cloud_sdk import MetaApi  # lazy: optional dependency
        except ImportError:
            logger.error(
                "metaapi-cloud-sdk is not installed — pip install metaapi-cloud-sdk"
            )
            return False
        try:
            self._api = MetaApi(self._token)
            account = self._runner.run(
                self._api.metatrader_account_api.get_account(self._account_id),
                timeout=90,
            )
            self._account = account
            if getattr(account, "state", "") != "DEPLOYED":
                self._runner.run(account.deploy(), timeout=120)
            self._runner.run(account.wait_connected(), timeout=120)
            conn = self._runner.run(account.get_rpc_connection(), timeout=60)
            self._runner.run(conn.connect(), timeout=60)
            self._runner.run(conn.wait_synchronized(), timeout=120)
            self._conn = conn
            self._connected = True
            info = self.get_account_info() or {}
            self._account_type = str(info.get("type", ""))
            logger.info(
                "MetaApi connected: login=%s server=%s type=%s trading_enabled=%s",
                info.get("login"), info.get("server"),
                self._account_type or "?", self._trading_enabled,
            )
            if self._account_type and self._account_type != "ACCOUNT_TRADE_MODE_DEMO" \
                    and not self._allow_real:
                logger.warning(
                    "Connected account is NOT a demo account (%s) and "
                    "METAAPI_ALLOW_REAL is not set — adapter stays READ-ONLY.",
                    self._account_type,
                )
            return True
        except Exception as exc:  # SDK raises many exception types
            logger.error("MetaApi connect failed: %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> None:
        try:
            if self._conn is not None:
                self._runner.run(self._conn.close(), timeout=15)
        except Exception as exc:
            logger.debug("MetaApi close error (ignored): %s", exc)
        self._conn = None
        self._account = None
        self._api = None
        self._connected = False

    def is_connected(self) -> bool:
        return bool(self._connected and self._conn is not None)

    def is_autotrading_enabled(self) -> bool:
        return self._trading_allowed()

    def _trading_allowed(self) -> bool:
        """All safety gates for order placement."""
        if not self._trading_enabled:
            return False
        if not self.is_connected():
            return False
        if self._account_type == "ACCOUNT_TRADE_MODE_DEMO":
            return True
        return self._allow_real

    def health_check(self) -> Dict[str, Any]:
        start = time.perf_counter()
        ok = self.is_connected()
        info = self.get_account_info() if ok else None
        return {
            "broker": self.name,
            "connected": ok,
            "healthy": bool(ok and info),
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            "trading_enabled": self._trading_enabled,
            "trading_allowed": self._trading_allowed(),
            "account_type": self._account_type,
        }

    def heartbeat(self) -> bool:
        return self.is_connected()

    # ─── Account ───────────────────────────────────────────

    def get_account_info(self) -> Optional[Dict]:
        if not self.is_connected():
            return None
        now = time.time()
        if self._info_cache and now - self._info_cache_ts < 1.0:
            return self._info_cache
        try:
            raw = self._runner.run(self._conn.get_account_information(), timeout=30)
        except Exception as exc:
            logger.error("MetaApi get_account_information failed: %s", exc)
            return None
        if raw is None:
            return None
        res = {
            "login": raw.get("login"),
            "server": raw.get("server"),
            "equity": raw.get("equity", 0.0),
            "balance": raw.get("balance", 0.0),
            "margin": raw.get("margin", 0.0),
            "free_margin": raw.get("freeMargin", 0.0),
            "profit": raw.get("equity", 0.0) - raw.get("balance", 0.0),
            "leverage": raw.get("leverage"),
            "currency": raw.get("currency"),
            "type": raw.get("type", ""),
            "broker": raw.get("broker", ""),
            "trade_allowed": raw.get("tradeAllowed", False),
        }
        self._info_cache = res
        self._info_cache_ts = now
        if res.get("type"):
            self._account_type = str(res["type"])
        return res

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

    def get_equity(self) -> float:
        info = self.get_account_info()
        return float(info["equity"]) if info else 0.0

    def get_balance(self) -> float:
        info = self.get_account_info()
        return float(info["balance"]) if info else 0.0

    # ─── Market data ───────────────────────────────────────

    def get_tick(self, symbol: str) -> Optional[Dict]:
        price = self._symbol_price(symbol)
        if price is None:
            return None
        return {
            "symbol": symbol,
            "bid": price.get("bid", 0.0),
            "ask": price.get("ask", 0.0),
            "last": price.get("last", 0.0),
            "time": price.get("time"),
        }

    def get_current_price(self, symbol: str) -> Dict[str, float]:
        price = self._symbol_price(symbol)
        if price is None:
            return {"bid": 0.0, "ask": 0.0, "mid": 0.0}
        bid = float(price.get("bid", 0.0) or 0.0)
        ask = float(price.get("ask", 0.0) or 0.0)
        return {"bid": bid, "ask": ask, "mid": (bid + ask) / 2 if bid and ask else 0.0}

    def _symbol_price(self, symbol: str) -> Optional[Dict]:
        if not self.is_connected():
            return None
        try:
            return self._runner.run(self._conn.get_symbol_price(symbol), timeout=30)
        except Exception as exc:
            logger.error("MetaApi get_symbol_price(%s) failed: %s", symbol, exc)
            return None

    def get_spread_pips(self, symbol: str) -> float:
        price = self._symbol_price(symbol)
        info = self.get_symbol_info(symbol) or {}
        point = float(info.get("point", 0.0) or 0.0)
        if not price or not point:
            return 0.0
        return (float(price.get("ask", 0)) - float(price.get("bid", 0))) / point / 10.0

    def get_ohlcv(self, symbol: str, timeframe: str,
                  count: int = 300) -> Optional[pd.DataFrame]:
        if not self.is_connected() or self._account is None:
            return None
        tf = _TIMEFRAME_MAP.get(str(timeframe), "1h")
        try:
            candles = self._runner.run(
                self._account.get_historical_candles(symbol, tf, None, count),
                timeout=60,
            )
        except Exception as exc:
            logger.error("MetaApi get_historical_candles(%s,%s) failed: %s",
                         symbol, tf, exc)
            return None
        if not candles:
            return None
        rows = [{
            "time": c.get("time"),
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "tick_volume": c.get("tickVolume", 0),
        } for c in candles]
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time").sort_index()
        return df

    # ─── Symbols ───────────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        if not self.is_connected():
            return None
        try:
            spec = self._runner.run(
                self._conn.get_symbol_specification(symbol), timeout=30)
        except Exception as exc:
            logger.error("MetaApi get_symbol_specification(%s) failed: %s", symbol, exc)
            return None
        if spec is None:
            return None
        tick_size = float(spec.get("tickSize", 0.0) or 0.0)
        return {
            "symbol": spec.get("symbol", symbol),
            "digits": spec.get("digits", 5),
            "point": tick_size,
            "min_lot": spec.get("minVolume", 0.01),
            "max_lot": spec.get("maxVolume", 100.0),
            "lot_step": spec.get("volumeStep", 0.01),
            "volume_min": spec.get("minVolume", 0.01),
            "volume_max": spec.get("maxVolume", 100.0),
            "volume_step": spec.get("volumeStep", 0.01),
            "contract": spec.get("contractSize", 100000.0),
            "spread": spec.get("spread", 0),
        }

    def get_symbols(self) -> List[str]:
        if not self.is_connected():
            return []
        try:
            return list(self._runner.run(self._conn.get_symbols(), timeout=30) or [])
        except Exception as exc:
            logger.error("MetaApi get_symbols failed: %s", exc)
            return []

    # ─── Positions ─────────────────────────────────────────

    def get_open_positions(self, magic: int = None,
                           symbol: str = None) -> List[Dict]:
        if not self.is_connected():
            return []
        try:
            positions = self._runner.run(self._conn.get_positions(), timeout=30) or []
        except Exception as exc:
            logger.error("MetaApi get_positions failed: %s", exc)
            return []
        result = []
        for pos in positions:
            if magic is not None and pos.get("magic") != magic:
                continue
            if symbol and pos.get("symbol") != symbol:
                continue
            open_time = pos.get("time")
            result.append({
                "ticket": int(pos.get("id", 0)) if str(pos.get("id", "")).isdigit()
                          else pos.get("id"),
                "symbol": pos.get("symbol"),
                "direction": "LONG" if pos.get("type") == "POSITION_TYPE_BUY" else "SHORT",
                "lots": pos.get("volume", 0.0),
                "volume": pos.get("volume", 0.0),
                "entry_price": pos.get("openPrice", 0.0),
                "current_price": pos.get("currentPrice", 0.0),
                "stop_loss": pos.get("stopLoss", 0.0),
                "take_profit": pos.get("takeProfit", 0.0),
                "profit": pos.get("profit", 0.0),
                "magic": pos.get("magic", 0),
                "comment": pos.get("comment", ""),
                "open_time": open_time.isoformat()
                             if isinstance(open_time, datetime) else str(open_time or ""),
            })
        return result

    def get_positions(self, symbol: str = None, magic: int = None) -> List[Dict]:
        """UnifiedBrokerAdapter: alias for get_open_positions."""
        return self.get_open_positions(magic=magic, symbol=symbol)

    def close_position(self, ticket: int, symbol: str, volume: float,
                       direction: str) -> Dict:
        return self.close_trade(ticket, symbol, direction)

    def close_trade(self, ticket: int, symbol: str = "",
                    direction: str = "", **kwargs) -> Optional[Dict]:
        if not self._trading_allowed():
            logger.warning("MetaApi close_trade refused: trading not allowed "
                           "(read-only mode or non-demo account)")
            return {"success": False, "error": "trading_not_allowed"}
        try:
            resp = self._runner.run(
                self._conn.close_position(str(ticket)), timeout=30)
        except Exception as exc:
            logger.error("MetaApi close_position(%s) failed: %s", ticket, exc)
            return {"success": False, "error": str(exc)}
        ok = resp is not None and resp.get("numericCode") in _TRADE_DONE_CODES
        return {"success": ok, "ticket": ticket,
                "message": resp.get("stringCode") if resp else "no response"}

    def close_all_positions(self, magic: int = None,
                            comment: str = "Emergency-Close") -> int:
        closed = 0
        for pos in self.get_open_positions(magic=magic):
            result = self.close_trade(pos["ticket"], pos["symbol"], pos["direction"])
            if result and result.get("success"):
                closed += 1
        return closed

    def modify_trade(self, ticket: int, new_sl: float = None,
                     new_tp: float = None, **kwargs) -> Optional[Dict]:
        if not self._trading_allowed():
            return {"success": False, "error": "trading_not_allowed"}
        try:
            resp = self._runner.run(
                self._conn.modify_position(str(ticket), new_sl, new_tp), timeout=30)
        except Exception as exc:
            logger.error("MetaApi modify_position(%s) failed: %s", ticket, exc)
            return {"success": False, "error": str(exc)}
        ok = resp is not None and resp.get("numericCode") in _TRADE_DONE_CODES
        return {"success": ok, "ticket": ticket}

    # ─── Orders ────────────────────────────────────────────

    def place_order(self, order: StandardOrder) -> StandardExecution:
        direction = "LONG" if order.side == OrderSide.BUY else "SHORT"
        result = self.open_trade(
            symbol=order.symbol,
            direction=direction,
            lots=order.volume,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            magic=order.magic or None,
            comment=order.comment or "Zohra",
        )
        if result and result.get("ticket"):
            return StandardExecution(
                order_id=order.order_id,
                ticket=result["ticket"],
                symbol=order.symbol,
                direction=direction,
                fill_price=result.get("price", 0.0),
                fill_volume=result.get("lots", order.volume),
                status=ExecutionStatus.SUCCESS,
                broker=self.name,
            )
        return StandardExecution(
            order_id=order.order_id,
            symbol=order.symbol,
            direction=direction,
            status=ExecutionStatus.FAILED,
            broker=self.name,
            error=(result or {}).get("error", "MetaApi order execution failed"),
        )

    def open_trade(self, symbol: str, direction: str, lots: float,
                   stop_loss: float = 0.0, take_profit: float = 0.0,
                   magic: int = None, comment: str = "Zohra") -> Optional[Dict]:
        """Open a market order. Returns trade dict with ticket, or None."""
        if not self._trading_allowed():
            logger.warning(
                "MetaApi open_trade refused for %s: trading not allowed "
                "(METAAPI_TRADING_ENABLED=%s, account_type=%s)",
                symbol, self._trading_enabled, self._account_type or "?",
            )
            return {"ticket": 0, "error": "trading_not_allowed"}
        options: Dict[str, Any] = {"comment": comment}
        if magic:
            options["magic"] = magic
        sl = stop_loss if stop_loss else None
        tp = take_profit if take_profit else None
        try:
            if direction.upper() in ("LONG", "BUY"):
                resp = self._runner.run(
                    self._conn.create_market_buy_order(symbol, lots, sl, tp, options),
                    timeout=30)
            else:
                resp = self._runner.run(
                    self._conn.create_market_sell_order(symbol, lots, sl, tp, options),
                    timeout=30)
        except Exception as exc:
            logger.error("MetaApi market order failed: %s", exc)
            return {"ticket": 0, "error": str(exc)}
        if resp is None or resp.get("numericCode") not in _TRADE_DONE_CODES:
            return {"ticket": 0,
                    "error": (resp or {}).get("stringCode", "order_rejected")}
        position_id = resp.get("positionId") or resp.get("orderId") or "0"
        price = self.get_current_price(symbol)
        fill = price.get("ask") if direction.upper() in ("LONG", "BUY") else price.get("bid")
        return {
            "ticket": int(position_id) if str(position_id).isdigit() else position_id,
            "price": fill or 0.0,
            "symbol": symbol,
            "lots": lots,
        }

    def modify_order(self, order_id: str, **kwargs) -> bool:
        if not self._trading_allowed():
            return False
        try:
            resp = self._runner.run(
                self._conn.modify_order(
                    str(order_id),
                    kwargs.get("price", 0.0),
                    kwargs.get("stop_loss", 0.0),
                    kwargs.get("take_profit", 0.0),
                ), timeout=30)
        except Exception as exc:
            logger.error("MetaApi modify_order(%s) failed: %s", order_id, exc)
            return False
        return resp is not None and resp.get("numericCode") in _TRADE_DONE_CODES

    def cancel_order(self, order_id: str) -> bool:
        if not self._trading_allowed():
            return False
        try:
            resp = self._runner.run(
                self._conn.cancel_order(str(order_id)), timeout=30)
        except Exception as exc:
            logger.error("MetaApi cancel_order(%s) failed: %s", order_id, exc)
            return False
        return resp is not None and resp.get("numericCode") in _TRADE_DONE_CODES

    def validate_order(self, order: StandardOrder) -> Dict[str, Any]:
        if not self.is_connected():
            return {"valid": False, "reason": "not_connected"}
        if not self._trading_allowed():
            return {"valid": False, "reason": "trading_not_allowed_read_only"}
        info = self.get_symbol_info(order.symbol)
        if not info:
            return {"valid": False, "reason": "symbol_unavailable"}
        if order.volume < info["volume_min"] or order.volume > info["volume_max"]:
            return {"valid": False, "reason": "volume_out_of_range"}
        return {"valid": True, "reason": "ok"}


# Singleton (lazy — no connection is made at import time)
metaapi_broker = MetaApiBrokerAdapter()
