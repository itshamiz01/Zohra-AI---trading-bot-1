"""
Setting up unified MetaTrader 5 broker adapter.
All MT5 calls are centralized here.

Upgraded to implement UnifiedBrokerAdapter from the Market Abstraction Layer.
All existing methods and behavior remain unchanged.
"""
# CRITICAL FIX: MT5 Error 10027 (AutoTrading disabled) detection and recovery

import os
import sys
import logging
import time as _time_module
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any

import pandas as pd
import numpy as np

# Resolve imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from zohra.brokers.interfaces import UnifiedBrokerAdapter
from zohra.brokers.models import (
    StandardOrder, StandardExecution, StandardTick,
    OrderSide, ExecutionStatus,
)
from zohra.brokers.broker_logger import log_broker_call
from zohra.config.settings import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER,
    MAGIC_SMC, MAGIC_SCALP,
    MIN_LOT_SIZE, MAX_LOT_SIZE, LOT_STEP,
    MT5_TERMINAL_PATH, BOT_NAME
)

logger = logging.getLogger("zohra.mt5")

from zohra.utils.mt5_connection import mt5, MT5_AVAILABLE


class MT5Broker(UnifiedBrokerAdapter):
    """
    Complete MT5 broker interface.
    Implements UnifiedBrokerAdapter for the Market Abstraction Layer.
    All existing methods preserved for backward compatibility.
    """

    def __init__(self):
        self._connected = False
        self._cache = {}

    @property
    def name(self) -> str:
        return "mt5"

    # ─── Connection ────────────────────────────────────────

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 package not installed.")
            return False

        import time

        # Check and enforce instance binding to MT5 Terminal A
        if MT5_TERMINAL_PATH and os.path.exists(MT5_TERMINAL_PATH):
            term = mt5.terminal_info()
            if term is not None:
                term_dir = os.path.normpath(term.path).lower()
                desired_dir = os.path.normpath(os.path.dirname(MT5_TERMINAL_PATH)).lower()
                if term_dir != desired_dir:
                    logger.warning(f"MT5: Active connection is bound to a different terminal ({term_dir}). Expected path: ({desired_dir}). Shutting down active connection...")
                    mt5.shutdown()
                    term = None

            if term is not None:
                # Login directly to the already open target terminal
                if mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
                    self._connected = True
                    self._cache["is_connected"] = (True, time.time())
                    return True
                else:
                    logger.warning(f"MT5 login failed: {mt5.last_error()} — attempting full re-initialization")
            
            # If not initialized or shutdown due to different terminal, initialize specifically with path
            logger.info(f"MT5: Binding exclusively to {BOT_NAME} at path: {MT5_TERMINAL_PATH}")
            init_success = False
            if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
                init_success = mt5.initialize(path=MT5_TERMINAL_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
                if not init_success:
                    logger.warning(f"MT5 init with credentials failed ({mt5.last_error()}) — attempting path-only initialization with active terminal account")
            
            if not init_success:
                init_success = mt5.initialize(path=MT5_TERMINAL_PATH)

            if not init_success:
                logger.error(f"MT5 init failed for path {MT5_TERMINAL_PATH}: {mt5.last_error()}")
                # Fallback to default pathless initialization
                if not mt5.initialize():
                    logger.error(f"MT5 fallback initialization also failed: {mt5.last_error()}")
                    return False
        else:
            # Fallback pathless initialization
            term = mt5.terminal_info()
            if term is not None:
                if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
                    if mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
                        self._connected = True
                        self._cache["is_connected"] = (True, time.time())
                        return True
                    else:
                        logger.warning(f"MT5 login failed: {mt5.last_error()} — attempting full re-initialization")

            init_success = False
            if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
                init_success = mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
            if not init_success:
                init_success = mt5.initialize()

            if not init_success:
                logger.error(f"MT5 init failed: {mt5.last_error()}")
                return False

        account = mt5.account_info()
        if account is None and MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            # Try explicit login if not already logged in
            if mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
                account = mt5.account_info()

        if account is None:
            logger.error(f"MT5: Could not get account info. Last error: {mt5.last_error()}")
            return False

        self._connected = True
        logger.info(f"✅ MT5 Connected: #{account.login} | {account.server} | "
                    f"${account.equity:.2f} equity")
        self._cache["is_connected"] = (True, time.time())

        # ═══ CRITICAL: Check AutoTrading is enabled ═══
        self._check_autotrading_status()

        return True

    def disconnect(self):
        if MT5_AVAILABLE:
            mt5.shutdown()
        self._connected = False
        self._cache["is_connected"] = (False, 0.0)
        logger.info("MT5 disconnected")

    def is_connected(self) -> bool:
        if not MT5_AVAILABLE:
            return False
            
        import time
        now = time.time()
        if "is_connected" in self._cache:
            val, ts = self._cache["is_connected"]
            if now - ts < 2.0:
                return val

        try:
            acc = None
            for _ in range(3):
                acc = mt5.account_info()
                if acc is not None:
                    break
                time.sleep(0.1)
                
            if acc is None:
                self._connected = False
                self._cache["is_connected"] = (False, now)
                return False
                
            term = mt5.terminal_info()
            if term is not None and not term.connected:
                logger.warning("MT5: Terminal is active but disconnected from trade server.")
                self._connected = False
                self._cache["is_connected"] = (False, now)
                return False
                
            self._connected = True
            self._cache["is_connected"] = (True, now)
            return True
        except Exception:
            self._connected = False
            self._cache["is_connected"] = (False, now)
            return False

    def is_autotrading_enabled(self) -> bool:
        """Check if Algo Trading (AutoTrading) is enabled in the MT5 terminal."""
        if not MT5_AVAILABLE:
            return False
        try:
            term = mt5.terminal_info()
            if term is not None:
                return bool(term.trade_allowed)
        except Exception:
            pass
        return False

    # ─── Account Info ──────────────────────────────────────

    def get_account_info(self) -> Optional[Dict]:
        if not MT5_AVAILABLE:
            return None
            
        import time
        now = time.time()
        if "account_info" in self._cache:
            val, ts = self._cache["account_info"]
            if now - ts < 1.0:
                return val

        account = mt5.account_info()
        if account is None:
            return None
            
        res = {
            "login":    account.login,
            "server":   account.server,
            "equity":   account.equity,
            "balance":  account.balance,
            "margin":   account.margin,
            "free_margin": account.margin_free,
            "profit":   account.profit,
            "leverage": account.leverage,
            "currency": account.currency,
        }
        self._cache["account_info"] = (res, now)
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
        return info['equity'] if info else 0.0

    def get_balance(self) -> float:
        info = self.get_account_info()
        return info['balance'] if info else 0.0

    # ─── Market Data ───────────────────────────────────────

    def get_ohlcv(self, symbol: str, timeframe_str: str, count: int = 300) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV bars from MT5.
        timeframe_str: "M1", "M5", "M15", "H1", "H4", "D1"
        """
        if not MT5_AVAILABLE:
            return None

        TF_MAP = {
            "M1":  mt5.TIMEFRAME_M1,  "M5":  mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1":  mt5.TIMEFRAME_H1,  "H4":  mt5.TIMEFRAME_H4,
            "D1":  mt5.TIMEFRAME_D1,  "W1":  mt5.TIMEFRAME_W1,
        }
        tf = TF_MAP.get(timeframe_str.upper(), mt5.TIMEFRAME_H1)

        if not mt5.symbol_select(symbol, True):
            logger.warning(f"Symbol {symbol} not available")
            return None

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) < min(10, count):
            logger.warning(f"No data for {symbol} {timeframe_str}")
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('time', inplace=True)
        df.rename(columns={
            'open': 'open', 'high': 'high', 'low': 'low',
            'close': 'close', 'real_volume': 'real_volume',
            'tick_volume': 'tick_volume'
        }, inplace=True)
        return df

    def get_candles(self, symbol: str, timeframe: str = "H1", count: int = 200) -> pd.DataFrame:
        df = self.get_ohlcv(symbol, timeframe, count)
        if df is None:
            return pd.DataFrame()
        df_reset = df.reset_index()
        df_reset.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df_reset

    def get_multi_tf(self, symbol: str, timeframes: List[str],
                     count: int = 300) -> Dict[str, Optional[pd.DataFrame]]:
        """Fetch multiple timeframes at once."""
        return {tf: self.get_ohlcv(symbol, tf, count) for tf in timeframes}

    def get_tick(self, symbol: str) -> Optional[Dict]:
        """Current bid/ask tick."""
        if not MT5_AVAILABLE:
            return None
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {"bid": tick.bid, "ask": tick.ask, "time": tick.time,
                "spread": tick.ask - tick.bid}

    def get_current_price(self, symbol: str) -> Dict[str, float]:
        tick = self.get_tick(symbol)
        if not tick:
            return {}
        return {
            "bid": tick["bid"],
            "ask": tick["ask"],
            "mid": (tick["bid"] + tick["ask"]) / 2,
            "spread": tick["spread"]
        }

    def get_spread_pips(self, symbol: str) -> float:
        """Get current spread in pips."""
        tick = self.get_tick(symbol)
        if not tick:
            return 999.0
        spread = tick['ask'] - tick['bid']
        if "JPY" in symbol:
            return spread * 100
        elif "XAU" in symbol:
            return spread * 10
        else:
            return spread * 10_000

    # ─── Filling Mode ──────────────────────────────────────

    def _get_filling(self, symbol: str) -> int:
        if not MT5_AVAILABLE:
            return 0
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_FOK
        fm = info.filling_mode
        if fm & 1: return mt5.ORDER_FILLING_FOK
        if fm & 2: return mt5.ORDER_FILLING_IOC
        if fm & 4: return mt5.ORDER_FILLING_RETURN
        return mt5.ORDER_FILLING_FOK

    # ─── AutoTrading Check ─────────────────────────────────

    def _check_autotrading_status(self):
        """Check if AutoTrading is enabled in the MT5 terminal and warn loudly if not."""
        if not MT5_AVAILABLE:
            return
        try:
            term = mt5.terminal_info()
            if term is not None:
                trade_allowed = getattr(term, 'trade_allowed', None)
                if trade_allowed is False:
                    logger.critical(
                        "\n"
                        "╔══════════════════════════════════════════════════════════════╗\n"
                        "║  🚨🚨🚨 AUTOTRADING IS DISABLED IN METATRADER 5 🚨🚨🚨      ║\n"
                        "║                                                              ║\n"
                        "║  The bot CANNOT place any trades until you fix this!         ║\n"
                        "║                                                              ║\n"
                        "║  HOW TO FIX:                                                 ║\n"
                        "║  1. Open your MetaTrader 5 terminal                          ║\n"
                        "║  2. Click the 'AutoTrading' button in the toolbar             ║\n"
                        "║     (or press Ctrl+E)                                        ║\n"
                        "║  3. The button should turn GREEN (currently RED/disabled)     ║\n"
                        "║  4. Also check: Tools → Options → Expert Advisors →          ║\n"
                        "║     ✅ 'Allow Algorithmic Trading' must be checked            ║\n"
                        "║                                                              ║\n"
                        "║  Error Code: 10027 (AutoTrading disabled by client)          ║\n"
                        "╚══════════════════════════════════════════════════════════════╝"
                    )
                    print("\n" + "!" * 60)
                    print("!!!  AUTOTRADING IS DISABLED — PRESS Ctrl+E IN MT5  !!!")
                    print("!" * 60 + "\n")
                    return False
                elif trade_allowed is True:
                    logger.info("✅ AutoTrading is ENABLED in MetaTrader 5 terminal.")
                    return True
        except Exception as e:
            logger.warning(f"Could not check AutoTrading status: {e}")
        return None

    def _try_enable_autotrading(self) -> bool:
        """Attempt to programmatically enable autotrading by re-initializing MT5."""
        if not MT5_AVAILABLE:
            return False
        try:
            # Shutdown and reinitialize - sometimes this resets the autotrading flag
            logger.info("🔄 Attempting to re-initialize MT5 connection to refresh AutoTrading state...")
            mt5.shutdown()
            import time as _time
            _time.sleep(1)
            
            if MT5_TERMINAL_PATH:
                result = mt5.initialize(
                    path=MT5_TERMINAL_PATH, 
                    login=MT5_LOGIN, 
                    password=MT5_PASSWORD, 
                    server=MT5_SERVER
                )
            else:
                result = mt5.initialize(
                    login=MT5_LOGIN, 
                    password=MT5_PASSWORD, 
                    server=MT5_SERVER
                )
            
            if not result:
                logger.error(f"MT5 re-initialization failed: {mt5.last_error()}")
                return False
            
            # Check again
            term = mt5.terminal_info()
            if term and getattr(term, 'trade_allowed', False):
                logger.info("✅ AutoTrading is now ENABLED after re-initialization!")
                self._connected = True
                return True
            else:
                logger.warning(
                    "⚠️ AutoTrading is STILL DISABLED after re-init. "
                    "You MUST manually press Ctrl+E in MT5 or enable it in Tools → Options → Expert Advisors."
                )
                self._connected = True  # Connection is fine, just can't trade
                return False
        except Exception as e:
            logger.error(f"Error during AutoTrading re-enable attempt: {e}")
            return False

    # ─── Order Execution ───────────────────────────────────

    def open_trade(self, symbol: str, direction: str, lots: float,
                   stop_loss: float, take_profit: float,
                   magic: int = None, comment: str = "Zohra") -> Optional[Dict]:
        """
        Open a market order.
        Returns trade dict with ticket, or None on failure.
        """
        # 0. Hard Symbol Guard check
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading disabled for {symbol}. Allowed symbols only.")
            return None

        if not MT5_AVAILABLE:
            logger.warning("MT5 not available — simulating trade open")
            return {"ticket": 99999, "price": 0, "symbol": symbol}

        if not mt5.symbol_select(symbol, True):
            logger.error(f"Cannot select {symbol}")
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"No tick data for {symbol}")
            return None

        # Snap lots to broker step
        lots = round(round(lots / LOT_STEP) * LOT_STEP, 2)
        lots = max(MIN_LOT_SIZE, min(lots, MAX_LOT_SIZE))

        # Precision & minimum stop level check
        info = mt5.symbol_info(symbol)
        digits = info.digits if info else (3 if "JPY" in symbol else 2 if "XAU" in symbol else 5)
        point = info.point if info else (0.001 if "JPY" in symbol else 0.01 if "XAU" in symbol else 0.00001)
        stops_level = getattr(info, "stops_level", 0) if info else 0
        min_stop_dist = max(stops_level * point, point * 10)

        clean_dir = str(direction).upper().strip()
        if clean_dir in ("LONG", "BUY"):
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            # Ensure SL is strictly below entry price
            if stop_loss > 0:
                if stop_loss >= price:
                    stop_loss = price - max(abs(price - stop_loss), min_stop_dist * 2)
                elif (price - stop_loss) < min_stop_dist:
                    stop_loss = price - min_stop_dist * 1.5
            # Ensure TP is strictly above entry price
            if take_profit > 0:
                if take_profit <= price:
                    take_profit = price + max(abs(take_profit - price), min_stop_dist * 2)
                elif (take_profit - price) < min_stop_dist:
                    take_profit = price + min_stop_dist * 1.5
        elif clean_dir in ("SHORT", "SELL"):
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            # Ensure SL is strictly above entry price
            if stop_loss > 0:
                if stop_loss <= price:
                    stop_loss = price + max(abs(stop_loss - price), min_stop_dist * 2)
                elif (stop_loss - price) < min_stop_dist:
                    stop_loss = price + min_stop_dist * 1.5
            # Ensure TP is strictly below entry price
            if take_profit > 0:
                if take_profit >= price:
                    take_profit = price - max(abs(price - take_profit), min_stop_dist * 2)
                elif (price - take_profit) < min_stop_dist:
                    take_profit = price - min_stop_dist * 1.5
        else:
            logger.error(f"Unknown order direction: {direction}")
            return None

        magic_num = magic or MAGIC_SMC
        sl_final = round(stop_loss, digits) if stop_loss > 0 else 0.0
        tp_final = round(take_profit, digits) if take_profit > 0 else 0.0
        price_final = round(price, digits)

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      symbol,
            "volume":      lots,
            "type":        order_type,
            "price":       price_final,
            "sl":          sl_final,
            "tp":          tp_final,
            "deviation":   10,
            "magic":       magic_num,
            "comment":     comment[:31],            # MT5 max 31 chars
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling(symbol),
        }

        # ── Pre-execution Order Check ──
        logger.info(f"📋 ORDER_REQUEST_CREATED: {clean_dir} {symbol} {lots}L @ {price_final} | SL={sl_final} TP={tp_final}")
        check_result = mt5.order_check(request)
        if check_result is not None and check_result.retcode != 0:
            logger.warning(f"⚠️ ORDER_CHECK_FAILED (retcode={check_result.retcode}): {check_result.comment} | MarginReq={getattr(check_result, 'margin', 'N/A')} | FreeMargin={getattr(check_result, 'margin_free', 'N/A')}")
            # If stops were invalid, retry with adjusted safety margin
            if check_result.retcode == 10016:
                logger.info("🔧 Auto-adjusting stops to meet broker minimum distance...")
                if order_type == mt5.ORDER_TYPE_BUY:
                    request["sl"] = round(price_final - (min_stop_dist * 3), digits)
                    request["tp"] = round(price_final + (min_stop_dist * 3), digits)
                else:
                    request["sl"] = round(price_final + (min_stop_dist * 3), digits)
                    request["tp"] = round(price_final - (min_stop_dist * 3), digits)
                logger.info(f"📋 REVISED_ORDER_REQUEST: {clean_dir} {symbol} SL={request['sl']} TP={request['tp']}")
        else:
            logger.info("✅ ORDER_CHECK_PASSED: Pre-execution broker validation successful.")

        result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            logger.error(f"❌ Order failed: mt5.order_send returned None. Last error: {err}")
            return None

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ TRADE OPENED: {symbol} {clean_dir} {lots}L @ {price_final} "
                        f"| SL={request['sl']} TP={request['tp']} | Ticket={result.order}")
            return {
                "ticket":    result.order,
                "symbol":    symbol,
                "direction": clean_dir,
                "lots":      lots,
                "price":     price_final,
                "stop_loss": request["sl"],
                "take_profit": request["tp"],
                "opened_at": datetime.utcnow().isoformat(),
            }
        elif result.retcode == 10027:
            # ═══ CRITICAL: AutoTrading is disabled in MT5 ═══
            logger.critical(
                f"🚨 ORDER BLOCKED — AutoTrading is DISABLED in MetaTrader 5! "
                f"Press Ctrl+E in MT5 terminal to enable it. (Error 10027)"
            )
            # Try to re-enable automatically
            if self._try_enable_autotrading():
                # Retry the order once after re-enabling
                logger.info("🔄 Retrying order after AutoTrading re-enable attempt...")
                # Refresh price
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    request["price"] = tick.ask if direction == "LONG" else tick.bid
                    price = request["price"]
                retry_result = mt5.order_send(request)
                if retry_result and retry_result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"✅ TRADE OPENED (after retry): {symbol} {direction} {lots}L @ {price} "
                                f"| SL={stop_loss} TP={take_profit} | Ticket={retry_result.order}")
                    return {
                        "ticket":    retry_result.order,
                        "symbol":    symbol,
                        "direction": direction,
                        "lots":      lots,
                        "price":     price,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "opened_at": datetime.utcnow().isoformat(),
                    }
                else:
                    ret = retry_result.retcode if retry_result else "None"
                    logger.error(f"❌ Retry also failed (retcode={ret}). AutoTrading is still disabled. Press Ctrl+E in MT5!")
            return None
        else:
            logger.error(f"❌ Order failed: {result.retcode} — {result.comment}")
            return None

    def open_position(self, order: Dict) -> Dict:
        symbol = order["symbol"]
        direction = order["direction"]
        lots = order.get("volume_lots") or (order.get("position_size", 1000) / 100_000)
        sl = order["stop_loss"]
        tp = order["take_profit"]
        comment = order.get("comment", "Zohra")
        magic = order.get("magic")

        res = self.open_trade(symbol, direction, lots, sl, tp, magic=magic, comment=comment)
        if not res:
            return {"success": False, "error": "MT5 deal failed", "retcode": None}
        return {"success": True, "mt5_ticket": res["ticket"], "fill_price": res["price"], "volume_lots": res["lots"]}

    def close_trade(self, ticket: int, symbol: str, direction: str,
                    lots: float = None, comment: str = "Zohra-Close") -> Optional[Dict]:
        """
        Close a position by ticket.
        If lots specified, closes partially.
        """
        if not MT5_AVAILABLE:
            return None

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logger.warning(f"No position found for ticket {ticket}")
            return None

        pos   = positions[0]
        close_lots = lots or pos.volume
        close_lots = round(close_lots, 2)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        # Close = opposite side
        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price      = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price      = tick.ask

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      symbol,
            "volume":      close_lots,
            "type":        order_type,
            "position":    ticket,
            "price":       price,
            "deviation":   10,
            "magic":       pos.magic,
            "comment":     comment[:31],
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling(symbol),
        }

        result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            logger.error(f"❌ Close failed: mt5.order_send returned None. Last error: {err}")
            return None

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            pnl   = pos.profit
            emoji = "✅" if pnl >= 0 else "❌"
            logger.info(f"{emoji} CLOSED {symbol} ticket={ticket} | P&L=${pnl:.2f} | {comment}")
            try:
                from zohra.core.portfolio_risk_coordinator import portfolio_risk_coordinator
                from zohra.config.settings import BOT_ID
                portfolio_risk_coordinator.register_closed_position(BOT_ID, ticket)
            except Exception:
                pass
            return {"success": True, "pnl": pnl, "price": price, "ticket": ticket}
        else:
            logger.error(f"❌ Close failed: {result.retcode} — {result.comment}")
            return None

    def close_position(self, ticket: int, symbol: str, volume: float, direction: str) -> Dict:
        res = self.close_trade(ticket, symbol, direction, lots=volume, comment="Zohra_Close")
        if not res:
            return {"success": False, "error": "MT5 close failed"}
        return {"success": True, "exit_price": res["price"], "profit_loss": res["pnl"]}

    def modify_trade(self, ticket: int, new_sl: float = None,
                     new_tp: float = None) -> bool:
        """Modify SL/TP on open position."""
        if not MT5_AVAILABLE:
            return True

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False

        pos = positions[0]
        sl  = round(new_sl, 5) if new_sl else pos.sl
        tp  = round(new_tp, 5) if new_tp else pos.tp

        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl":       sl,
            "tp":       tp,
        }
        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            logger.error(f"❌ Modify failed: mt5.order_send returned None. Last error: {err}")
            return False
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"🔄 Modified ticket={ticket}: SL={sl} TP={tp}")
            return True
        else:
            logger.error(f"❌ Modify failed: {result.retcode}")
            return False

    def modify_stop(self, ticket: int, symbol: str, stop_loss: float, take_profit: Optional[float] = None) -> Dict:
        ok = self.modify_trade(ticket, new_sl=stop_loss, new_tp=take_profit)
        return {"success": ok, "error": None if ok else "MT5 modification failed"}

    # ─── Position Queries ──────────────────────────────────

    def get_open_positions(self, magic: int = None,
                           symbol: str = None) -> List[Dict]:
        """Get all open positions, optionally filtered."""
        if not MT5_AVAILABLE:
            return []

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        result = []
        for pos in positions:
            if magic and pos.magic != magic:
                continue
            result.append({
                "ticket":     pos.ticket,
                "symbol":     pos.symbol,
                "direction":  "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT",
                "lots":       pos.volume,
                "volume":     pos.volume,
                "entry_price": pos.price_open,
                "current_price": pos.price_current,
                "stop_loss":  pos.sl,
                "take_profit": pos.tp,
                "profit":     pos.profit,
                "magic":      pos.magic,
                "comment":    pos.comment,
                "open_time":  datetime.utcfromtimestamp(pos.time).isoformat(),
            })
        return result

    def close_all_positions(self, magic: int = None, comment: str = "Emergency-Close") -> int:
        """Close all open positions. Returns count closed."""
        positions = self.get_open_positions(magic=magic)
        closed = 0
        for pos in positions:
            result = self.close_trade(
                pos['ticket'], pos['symbol'], pos['direction'], comment=comment
            )
            if result and result.get('success'):
                closed += 1
        return closed

    # ─── Symbol Info ───────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        if not MT5_AVAILABLE:
            return None
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        return {
            "symbol":    info.name,
            "digits":    info.digits,
            "point":     info.point,
            "min_lot":   info.volume_min,
            "max_lot":   info.volume_max,
            "lot_step":  info.volume_step,
            # Aliases used by zohra.py lot-snapping logic
            "volume_min":  info.volume_min,
            "volume_max":  info.volume_max,
            "volume_step": info.volume_step,
            "contract":  info.trade_contract_size,
            "spread":    info.spread,
        }

    # ─── Interface Compliance Methods (MAL) ────────────────

    def place_order(self, order: StandardOrder) -> StandardExecution:
        """UnifiedBrokerAdapter: place a standardized order."""
        direction = "LONG" if order.side == OrderSide.BUY else "SHORT"
        result = self.open_trade(
            symbol=order.symbol,
            direction=direction,
            lots=order.volume,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            magic=order.magic or MAGIC_SMC,
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
            error="MT5 order execution failed",
        )

    def modify_order(self, order_id: str, **kwargs) -> bool:
        """UnifiedBrokerAdapter: modify pending order. MT5 uses ticket-based modification."""
        ticket = kwargs.get("ticket", 0)
        if not ticket:
            try:
                ticket = int(order_id)
            except (ValueError, TypeError):
                return False
        return self.modify_trade(
            ticket,
            new_sl=kwargs.get("stop_loss"),
            new_tp=kwargs.get("take_profit"),
        )

    def cancel_order(self, order_id: str) -> bool:
        """UnifiedBrokerAdapter: cancel pending order. MT5 doesn't distinguish pending orders in this adapter."""
        logger.warning(f"cancel_order({order_id}): MT5 pending order cancellation not implemented in this adapter.")
        return False

    def get_positions(self, symbol: str = None, magic: int = None) -> List[Dict]:
        """UnifiedBrokerAdapter: alias for get_open_positions."""
        return self.get_open_positions(magic=magic, symbol=symbol)

    def health_check(self) -> Dict[str, Any]:
        """UnifiedBrokerAdapter: comprehensive health check."""
        start = _time_module.perf_counter()
        connected = self.is_connected()
        latency = (_time_module.perf_counter() - start) * 1000

        details = {}
        if connected:
            account = self.get_account_info()
            if account:
                details["login"] = account.get("login")
                details["server"] = account.get("server")
                details["equity"] = account.get("equity")
            autotrading = self.is_autotrading_enabled()
            details["autotrading_enabled"] = autotrading

        return {
            "broker": self.name,
            "status": "healthy" if connected else "unhealthy",
            "connected": connected,
            "latency_ms": round(latency, 2),
            "details": details,
        }

    def heartbeat(self) -> bool:
        """UnifiedBrokerAdapter: lightweight connectivity ping."""
        if not MT5_AVAILABLE:
            return False
        try:
            acc = mt5.account_info()
            return acc is not None
        except Exception:
            return False

    def validate_order(self, order: StandardOrder) -> Dict[str, Any]:
        """UnifiedBrokerAdapter: pre-flight order validation."""
        reasons = []
        if not MT5_AVAILABLE:
            return {"valid": False, "reason": "MT5 not available"}

        # Check symbol availability
        if not mt5.symbol_select(order.symbol, True):
            reasons.append(f"Symbol {order.symbol} not available")

        # Check volume bounds
        info = self.get_symbol_info(order.symbol)
        if info:
            if order.volume < info.get("min_lot", MIN_LOT_SIZE):
                reasons.append(f"Volume {order.volume} below minimum {info['min_lot']}")
            if order.volume > info.get("max_lot", MAX_LOT_SIZE):
                reasons.append(f"Volume {order.volume} above maximum {info['max_lot']}")

        # Check autotrading
        if not self.is_autotrading_enabled():
            reasons.append("AutoTrading is disabled in MT5 terminal")

        if reasons:
            return {"valid": False, "reason": "; ".join(reasons)}
        return {"valid": True, "reason": ""}

    def get_symbols(self) -> List[str]:
        """UnifiedBrokerAdapter: get all available MT5 symbols."""
        if not MT5_AVAILABLE:
            return []
        try:
            symbols = mt5.symbols_get()
            if symbols:
                return [s.name for s in symbols if s.visible]
        except Exception:
            pass
        return []


# Singleton
mt5_broker = MT5Broker()
