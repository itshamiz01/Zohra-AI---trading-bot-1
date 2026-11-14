"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — ISOLATED ACCOUNT WORKER                           ║
║     Each worker owns EXACTLY ONE MT5 account connection             ║
╚══════════════════════════════════════════════════════════════════════╝

Account Workers are execution-only processes:
  - They receive authorized execution.request messages from the Risk Engine
  - They convert requests into MT5 order_send() calls
  - They return execution.result messages
  - They periodically publish account.snapshot messages

CRITICAL BOUNDARY RULES:
  Worker 1 can ONLY interact with Account 1
  Worker 2 can ONLY interact with Account 2
  Worker 3 can ONLY interact with Account 3

  Workers must NEVER:
  - Login to another account
  - Access strategy internals or source code
  - Make independent trading decisions
  - Receive unrestricted global decision authority

  Workers SHOULD:
  - Query positions_get(), orders_get(), account_info() from THEIR MT5 connection
  - Manage position lifecycle (close, modify SL/TP, trailing stops) via management commands
  - Publish normalized position events to the message bus
"""

import os
import sys
import logging
import asyncio
import time
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from zohra.core.message_bus import (
    message_bus, ZohraMessage, MessageTopic,
    ExecutionStatus, KillSwitchLevel
)
from zohra.config.settings import (
    AccountConfig,
    MIN_LOT_SIZE, MAX_LOT_SIZE, LOT_STEP,
    MAGIC_SMC, MAGIC_SCALP,
    MANAGE_INTERVAL_SEC,
)

logger = logging.getLogger("zohra.account_worker")


class AccountWorker:
    """
    Isolated MT5 Account Worker.

    Each instance owns exactly ONE MT5 terminal connection and manages
    all trade execution for that single account.

    Process isolation guarantee:
    - The MT5 Python API connects to a specific terminal instance
    - Each terminal has one current account context
    - Multiple terminals are isolated by targeting different terminal paths

    Never allow:
        Worker 1 → login Account 2
        Worker 2 → login Account 3
    This prevents account-context contamination.
    """

    SNAPSHOT_INTERVAL_SEC = 10.0  # Publish account snapshot every 10s
    MANAGE_INTERVAL_SEC = 3.0     # Fast position management & profit banking every 3s

    def __init__(self, account_config: AccountConfig):
        self.config = account_config
        self.account_id = account_config.account_id
        self.process_name = f"zohra-account-{account_config.account_id}"

        self._running = False
        self._start_time = 0.0
        self._mt5 = None      # MT5 module reference (isolated per worker)
        self._connected = False
        self._killed = False   # Account-level kill switch

        # ─── Trade Tracking ───
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._executions: Dict[str, Dict] = {}  # request_id → result

        # ─── Subscribe to messages ───
        self._setup_subscriptions()

        logger.info(
            f"AccountWorker initialized: {self.account_id} | "
            f"Login: {account_config.login} | "
            f"Terminal: {account_config.terminal_path}"
        )

    def _setup_subscriptions(self):
        """Subscribe to execution requests targeted at this account."""
        # Only receive execution requests targeted to this specific account
        message_bus.subscribe(
            MessageTopic.EXECUTION_REQUEST.value,
            self._on_execution_request,
            subscriber_id=self.account_id,
            filter_fn=lambda msg: msg.payload.get("account_id") == self.account_id,
        )
        # Kill switch
        message_bus.subscribe(
            MessageTopic.TRADING_KILL_SWITCH.value,
            self._on_kill_switch,
            subscriber_id=f"{self.account_id}_kill",
        )

    # ═══════════════════════════════════════════════════════════
    #  MT5 CONNECTION (ISOLATED)
    # ═══════════════════════════════════════════════════════════

    def connect(self) -> bool:
        """
        Connect to THIS account's specific MT5 terminal.

        CRITICAL: Each worker MUST use its own terminal path to prevent
        account-context contamination. The MT5 Python API's initialize()
        function binds to a specific terminal instance.
        """
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            logger.error(f"[{self.account_id}] MetaTrader5 package not installed")
            return False

        terminal_path = self.config.terminal_path

        # Shutdown any existing connection first
        try:
            self._mt5.shutdown()
        except Exception:
            pass

        # Initialize with THIS account's terminal path
        logger.info(f"[{self.account_id}] Connecting to MT5 terminal: {terminal_path}")

        init_success = False
        if terminal_path and self.config.login and self.config.password:
            init_success = self._mt5.initialize(
                path=terminal_path,
                login=self.config.login,
                password=self.config.password,
                server=self.config.server,
            )
            if not init_success:
                logger.warning(
                    f"[{self.account_id}] MT5 init with full credentials failed: "
                    f"{self._mt5.last_error()} — trying path-only"
                )

        if not init_success and terminal_path:
            init_success = self._mt5.initialize(path=terminal_path)

        if not init_success:
            # Last resort: default initialization
            init_success = self._mt5.initialize()
            if init_success and self.config.login:
                if not self._mt5.login(
                    login=self.config.login,
                    password=self.config.password,
                    server=self.config.server,
                ):
                    logger.error(f"[{self.account_id}] MT5 login failed: {self._mt5.last_error()}")
                    return False

        if not init_success:
            logger.error(f"[{self.account_id}] MT5 initialization failed: {self._mt5.last_error()}")
            return False

        # Verify we're connected to the RIGHT account
        account = self._mt5.account_info()
        if account is None:
            logger.error(f"[{self.account_id}] Cannot get account info after init")
            return False

        if account.login != self.config.login:
            logger.critical(
                f"[{self.account_id}] ACCOUNT CONTAMINATION DETECTED! "
                f"Expected login {self.config.login}, got {account.login}. ABORTING."
            )
            self._mt5.shutdown()
            return False

        self._connected = True
        logger.info(
            f"✅ [{self.account_id}] Connected: #{account.login} | {account.server} | "
            f"${account.equity:.2f} equity"
        )

        # Check AutoTrading
        term = self._mt5.terminal_info()
        if term and not term.trade_allowed:
            logger.critical(
                f"🚨 [{self.account_id}] AutoTrading is DISABLED! "
                f"Press Ctrl+E in the MT5 terminal at {terminal_path}"
            )

        return True

    def disconnect(self):
        """Disconnect from this account's MT5 terminal."""
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._connected = False
        logger.info(f"[{self.account_id}] Disconnected from MT5")

    def is_connected(self) -> bool:
        """Check if still connected to the correct account."""
        if not self._mt5 or not self._connected:
            return False
        try:
            acc = self._mt5.account_info()
            if acc is None:
                self._connected = False
                return False
            if acc.login != self.config.login:
                logger.critical(f"[{self.account_id}] Account mismatch! Expected {self.config.login}, got {acc.login}")
                self._connected = False
                return False
            return True
        except Exception:
            self._connected = False
            return False

    # ═══════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═══════════════════════════════════════════════════════════

    def start(self) -> bool:
        if not self.connect():
            return False
        self._running = True
        self._start_time = time.time()
        logger.info(f"✅ [{self.account_id}] AccountWorker started")
        return True

    def stop(self):
        self._running = False
        self.disconnect()
        logger.info(f"[{self.account_id}] AccountWorker stopped")

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    # ═══════════════════════════════════════════════════════════
    #  MAIN LOOP
    # ═══════════════════════════════════════════════════════════

    async def run_loop(self):
        """Main async loop — publishes snapshots, manages positions, sends heartbeats."""
        last_snapshot = 0.0
        last_manage = 0.0

        while self._running:
            try:
                now = time.time()

                # ─── Account Snapshot ───
                if now - last_snapshot >= self.SNAPSHOT_INTERVAL_SEC:
                    await self._publish_account_snapshot()
                    last_snapshot = now

                # ─── Position Management ───
                if now - last_manage >= self.MANAGE_INTERVAL_SEC:
                    await self._manage_positions()
                    last_manage = now

                # ─── Heartbeat ───
                status = "HEALTHY" if self._connected and not self._killed else "DEGRADED"
                if self._killed:
                    status = "KILLED"
                await message_bus.publish_heartbeat(self.process_name, status, self.uptime)

                # ─── Connection health check ───
                if not self.is_connected():
                    logger.warning(f"[{self.account_id}] Connection lost — attempting reconnect...")
                    self.connect()

                await asyncio.sleep(2.0)

            except Exception as e:
                logger.error(f"[{self.account_id}] Worker loop error: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    # ═══════════════════════════════════════════════════════════
    #  EXECUTION HANDLER
    # ═══════════════════════════════════════════════════════════

    async def _on_execution_request(self, msg: ZohraMessage):
        """Handle an authorized execution request from the Risk Engine."""
        if self._killed:
            logger.warning(f"[{self.account_id}] Kill switch active — rejecting execution")
            return

        if not self._connected:
            logger.error(f"[{self.account_id}] Not connected — cannot execute")
            return

        payload = msg.payload
        request_id = payload.get("request_id", "")
        signal_id = payload.get("signal_id", "")
        strategy_id = payload.get("strategy_id", "")
        symbol = payload.get("symbol", "")
        direction = payload.get("direction", "")
        volume = payload.get("volume", 0.0)
        stop_loss = payload.get("stop_loss", 0.0)
        take_profit = payload.get("take_profit", 0.0)
        max_slippage = payload.get("max_slippage", 20)

        # ─── Safeguard: Prevent position stacking on the same symbol ───
        open_sym_positions = self._mt5.positions_get(symbol=symbol)
        if open_sym_positions and len(open_sym_positions) >= 1:
            logger.warning(
                f"🛡️ [{self.account_id}] Stacking veto: Already have {len(open_sym_positions)} open position(s) "
                f"on {symbol} — rejecting duplicate execution"
            )
            return

        logger.info(
            f"📥 [{self.account_id}] Executing: {direction} {symbol} "
            f"Vol={volume} SL={stop_loss} TP={take_profit}"
        )

        # ─── Execute via MT5 ───
        result = self._execute_order(
            symbol=symbol,
            direction=direction,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            magic=MAGIC_SMC + self.config.magic_offset,
            comment=f"Z_{strategy_id[:15]}",
            deviation=max_slippage,
        )

        # ─── Publish execution result ───
        exec_msg = ZohraMessage(
            message_type=MessageTopic.EXECUTION_RESULT.value,
            payload={
                "request_id": request_id,
                "signal_id": signal_id,
                "account_id": self.account_id,
                "strategy_id": strategy_id,
                "status": result.get("status", ExecutionStatus.FAILED.value),
                "order_ticket": result.get("ticket", 0),
                "deal_ticket": result.get("deal", 0),
                "volume": result.get("volume", volume),
                "price": result.get("price", 0.0),
                "symbol": symbol,
                "direction": direction,
                "error": result.get("error", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            source=self.process_name,
        )
        await message_bus.publish(exec_msg)

        if result.get("status") == ExecutionStatus.FILLED.value:
            self._daily_trades += 1
            logger.info(
                f"✅ [{self.account_id}] FILLED: {direction} {symbol} Vol={volume} "
                f"@ {result.get('price')} | Ticket={result.get('ticket')}"
            )
        else:
            logger.warning(
                f"❌ [{self.account_id}] EXECUTION FAILED: {result.get('error', 'Unknown')} "
                f"| Status={result.get('status')}"
            )

    def _execute_order(self, symbol: str, direction: str, volume: float,
                       stop_loss: float, take_profit: float,
                       magic: int = None, comment: str = "Zohra",
                       deviation: int = 20) -> Dict[str, Any]:
        """Execute a market order via MT5 on THIS account's connection."""
        mt5 = self._mt5
        if not mt5:
            return {"status": ExecutionStatus.FAILED.value, "error": "MT5 not available"}

        # Select symbol
        if not mt5.symbol_select(symbol, True):
            return {"status": ExecutionStatus.FAILED.value, "error": f"Cannot select symbol {symbol}"}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"status": ExecutionStatus.FAILED.value, "error": f"No tick data for {symbol}"}

        # Symbol info for precision
        info = mt5.symbol_info(symbol)
        digits = info.digits if info else 5
        point = info.point if info else 0.00001

        # Snap lots
        volume = round(round(volume / LOT_STEP) * LOT_STEP, 2)
        volume = max(MIN_LOT_SIZE, min(volume, MAX_LOT_SIZE))

        # Determine order type and price
        clean_dir = direction.upper().strip()
        if clean_dir in ("LONG", "BUY"):
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        elif clean_dir in ("SHORT", "SELL"):
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            return {"status": ExecutionStatus.FAILED.value, "error": f"Unknown direction: {direction}"}

        # Double-check existing open positions on MT5 to strictly prevent self-hedging
        current_positions = self._mt5.positions_get(symbol=symbol)
        if current_positions:
            for p in current_positions:
                if p.type != order_type:
                    logger.critical(
                        f"[{self.account_id}] 🛑 VETO: Opposing position #{p.ticket} "
                        f"({'BUY' if p.type==0 else 'SELL'}) already open on {symbol}! "
                        f"Execution of {clean_dir} aborted to prevent self-hedging."
                    )
                    return {"status": ExecutionStatus.REJECTED.value, "error": f"Opposing position already open on {symbol}"}

        # Get filling mode
        filling = mt5.ORDER_FILLING_FOK
        if info:
            fm = info.filling_mode
            if fm & 1:
                filling = mt5.ORDER_FILLING_FOK
            elif fm & 2:
                filling = mt5.ORDER_FILLING_IOC
            elif fm & 4:
                filling = mt5.ORDER_FILLING_RETURN

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": round(price, digits),
            "sl": round(stop_loss, digits) if stop_loss > 0 else 0.0,
            "tp": round(take_profit, digits) if take_profit > 0 else 0.0,
            "deviation": deviation,
            "magic": magic or MAGIC_SMC,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            return {"status": ExecutionStatus.FAILED.value, "error": f"order_send returned None: {err}"}

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return {
                "status": ExecutionStatus.FILLED.value,
                "ticket": result.order,
                "deal": result.deal,
                "volume": volume,
                "price": round(price, digits),
            }
        elif result.retcode == 10027:
            return {
                "status": ExecutionStatus.REJECTED.value,
                "error": "AutoTrading is DISABLED. Press Ctrl+E in MT5!",
            }
        else:
            return {
                "status": ExecutionStatus.REJECTED.value,
                "error": f"Retcode {result.retcode}: {result.comment}",
            }

    # ═══════════════════════════════════════════════════════════
    #  ACCOUNT SNAPSHOT
    # ═══════════════════════════════════════════════════════════

    async def _publish_account_snapshot(self):
        """Publish current account state to the message bus with accurate daily P&L."""
        if not self._mt5 or not self._connected:
            return

        try:
            account = self._mt5.account_info()
            if account is None:
                return

            # Calculate today's realized PnL from MT5 deals (naive local/server time)
            now_dt = datetime.now()
            start_of_day = datetime(now_dt.year, now_dt.month, now_dt.day, 0, 0, 0)
            end_of_day = datetime(now_dt.year, now_dt.month, now_dt.day, 23, 59, 59)
            deals = self._mt5.history_deals_get(start_of_day, end_of_day)
            closed_pnl = 0.0
            if deals:
                for d in deals:
                    if d.entry in (1, 2, 3):  # DEAL_ENTRY_OUT / INOUT / OUT_BY
                        closed_pnl += (d.profit + d.commission + d.swap)
            self._daily_pnl = round(closed_pnl, 2)

            # Check if daily profit target ($50.00) is reached
            from zohra.config.settings import DAILY_PROFIT_TARGET
            if self._daily_pnl >= DAILY_PROFIT_TARGET and not getattr(self, "_daily_target_achieved", False):
                self._daily_target_achieved = True
                logger.info(
                    f"🎯 [{self.account_id}] DAILY TARGET REACHED! ${self._daily_pnl:.2f} >= ${DAILY_PROFIT_TARGET:.2f} today! "
                    f"Pausing new trades for today to bank profits."
                )

            # Get open positions count and details
            positions = self._mt5.positions_get()
            open_count = len(positions) if positions else 0
            pos_list = []
            if positions:
                for p in positions:
                    ptype = "BUY" if p.type == 0 else ("SELL" if p.type == 1 else str(p.type))
                    pos_list.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "direction": ptype,
                        "volume": p.volume,
                        "profit": p.profit,
                        "magic": p.magic,
                    })

            msg = ZohraMessage(
                message_type=MessageTopic.ACCOUNT_SNAPSHOT.value,
                payload={
                    "account_id": self.account_id,
                    "login": account.login,
                    "balance": account.balance,
                    "equity": account.equity,
                    "margin": account.margin,
                    "free_margin": account.margin_free,
                    "profit": account.profit,
                    "open_positions": open_count,
                    "positions": pos_list,
                    "daily_pnl": self._daily_pnl,
                    "daily_trades": self._daily_trades,
                    "trade_allowed": not getattr(self, "_daily_target_achieved", False),
                    "connection_status": "ONLINE",
                },
                source=self.process_name,
            )
            await message_bus.publish(msg)

        except Exception as e:
            logger.warning(f"[{self.account_id}] Snapshot error: {e}")

    # ═══════════════════════════════════════════════════════════
    #  POSITION MANAGEMENT (Active Profit Banking at $3-$4, Max $5)
    # ═══════════════════════════════════════════════════════════

    async def _manage_positions(self):
        """Manage open positions on this account (banking profits and moving to breakeven)."""
        if not self._mt5 or not self._connected:
            return

        try:
            positions = self._mt5.positions_get()
            if not positions:
                return

            from zohra.config.settings import (
                SCALP_TARGET_PROFIT_DEFAULT,
                SCALP_TARGET_PROFIT_FOREX,
                SCALP_TARGET_PROFIT_MAX,
                SCALP_FOREX_BE_TRIGGER,
                SCALP_JPY_BE_TRIGGER,
                XAUUSD_BIG_TRADE_BE_TRIGGER,
                XAUUSD_BIG_TRADE_TP_CEILING,
            )

            for pos in positions:
                current_profit = pos.profit
                clean_sym = pos.symbol.upper()
                is_gold = "XAU" in clean_sym or "GOLD" in clean_sym

                # ─── CASE A: BIG TRADES (XAUUSD / Gold) ───
                if is_gold:
                    # 1. HARD CEILING EXIT / BIG TARGET BANKING ($35.00+):
                    if current_profit >= XAUUSD_BIG_TRADE_TP_CEILING:
                        logger.info(
                            f"💰 [{self.account_id}] GOLD BIG TARGET HIT: Position #{pos.ticket} on {pos.symbol} "
                            f"reached ${current_profit:.2f}! Closing trade to bank large profit."
                        )
                        self._close_position(pos, f"TP_BigTrade_${current_profit:.2f}")
                        continue

                    # 2. BREAKEVEN PROTECTION AT $8.00 PROFIT:
                    # Do NOT close at $3.50! Let Gold run, but lock Breakeven once up $8.00.
                    if current_profit >= XAUUSD_BIG_TRADE_BE_TRIGGER:
                        self._move_to_breakeven(pos, buffer_points=100)  # 1.0 point ($1.00) locked in

                # ─── CASE B: FOREX SCALPING (USDJPY, GBPJPY, EURUSD, GBPUSD) ───
                else:
                    is_jpy = "JPY" in clean_sym
                    target_profit = SCALP_TARGET_PROFIT_DEFAULT if is_jpy else SCALP_TARGET_PROFIT_FOREX  # $3.50 for JPY, $2.20 for EUR/GBP
                    be_trigger = SCALP_JPY_BE_TRIGGER if is_jpy else SCALP_FOREX_BE_TRIGGER              # $2.00 for JPY, $1.20 for EUR/GBP

                    # 1. IMMEDIATE SCALP PROFIT BANKING ($2.20 - $3.50):
                    if current_profit >= target_profit:
                        logger.info(
                            f"💰 [{self.account_id}] BANKING SCALP PROFIT: Position #{pos.ticket} on {pos.symbol} "
                            f"reached ${current_profit:.2f} (Target: ${target_profit:.2f})! Closing scalp."
                        )
                        self._close_position(pos, f"TP_Scalp_${current_profit:.2f}")
                        continue

                    # 2. HARD CEILING EXIT (Max $5.00):
                    if current_profit >= SCALP_TARGET_PROFIT_MAX:
                        logger.info(
                            f"💰 [{self.account_id}] MAX PROFIT CEILING HIT: Position #{pos.ticket} on {pos.symbol} "
                            f"reached ${current_profit:.2f}! Closing scalp immediately."
                        )
                        self._close_position(pos, f"TP_Max_${current_profit:.2f}")
                        continue

                    # 3. FAST BREAKEVEN PROTECTION:
                    # Lock SL to breakeven + buffer so winning scalps never turn red!
                    if current_profit >= be_trigger:
                        self._move_to_breakeven(pos)

                # Publish position event
                pos_msg = ZohraMessage(
                    message_type=MessageTopic.ACCOUNT_POSITION.value,
                    payload={
                        "account_id": self.account_id,
                        "ticket": pos.ticket,
                        "symbol": pos.symbol,
                        "direction": "LONG" if pos.type == 0 else "SHORT",
                        "volume": pos.volume,
                        "entry_price": pos.price_open,
                        "current_price": pos.price_current,
                        "stop_loss": pos.sl,
                        "take_profit": pos.tp,
                        "profit": pos.profit,
                        "magic": pos.magic,
                        "comment": pos.comment,
                    },
                    source=self.process_name,
                )
                await message_bus.publish(pos_msg)

        except Exception as e:
            logger.warning(f"[{self.account_id}] Position management error: {e}")

    def _close_position(self, pos, comment="Close Scalp") -> bool:
        """Close an open position via MT5 market order."""
        if not self._mt5:
            return False
        try:
            tick = self._mt5.symbol_info_tick(pos.symbol)
            if not tick:
                return False

            close_type = self._mt5.ORDER_TYPE_SELL if pos.type == 0 else self._mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == 0 else tick.ask

            info = self._mt5.symbol_info(pos.symbol)
            filling = self._mt5.ORDER_FILLING_FOK
            if info:
                fm = info.filling_mode
                if fm & 1:
                    filling = self._mt5.ORDER_FILLING_FOK
                elif fm & 2:
                    filling = self._mt5.ORDER_FILLING_IOC
                elif fm & 4:
                    filling = self._mt5.ORDER_FILLING_RETURN

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": pos.magic,
                "comment": comment[:31],
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            res = self._mt5.order_send(request)
            if res and res.retcode == self._mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ [{self.account_id}] Successfully closed #{pos.ticket} on {pos.symbol} | Profit: ${pos.profit:.2f}")
                return True
            elif res:
                request["type_filling"] = self._mt5.ORDER_FILLING_IOC
                res2 = self._mt5.order_send(request)
                if res2 and res2.retcode == self._mt5.TRADE_RETCODE_DONE:
                    logger.info(f"✅ [{self.account_id}] Successfully closed #{pos.ticket} on {pos.symbol} | Profit: ${pos.profit:.2f}")
                    return True
                logger.warning(f"❌ [{self.account_id}] Failed to close #{pos.ticket}: {res.comment}")
            return False
        except Exception as e:
            logger.error(f"[{self.account_id}] Error closing #{pos.ticket}: {e}")
            return False

    def _move_to_breakeven(self, pos, buffer_points: int = 20) -> bool:
        """Move position SL to breakeven + buffer once in profit."""
        if not self._mt5:
            return False
        try:
            info = self._mt5.symbol_info(pos.symbol)
            digits = info.digits if info else 5
            point = info.point if info else 0.00001

            buffer = buffer_points * point
            is_buy = pos.type == 0
            new_sl = round(pos.price_open + buffer if is_buy else pos.price_open - buffer, digits)

            if is_buy and (pos.sl >= new_sl or pos.sl >= pos.price_open):
                return False
            if not is_buy and pos.sl > 0 and (pos.sl <= new_sl or pos.sl <= pos.price_open):
                return False

            req = {
                "action": self._mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": pos.ticket,
                "sl": new_sl,
                "tp": pos.tp,
            }
            res = self._mt5.order_send(req)
            if res and res.retcode == self._mt5.TRADE_RETCODE_DONE:
                logger.info(f"🛡️ [{self.account_id}] Moved #{pos.ticket} {pos.symbol} to Breakeven+ (SL={new_sl})")
                return True
            return False
        except Exception as e:
            logger.debug(f"[{self.account_id}] Breakeven move error: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    #  KILL SWITCH
    # ═══════════════════════════════════════════════════════════

    async def _on_kill_switch(self, msg: ZohraMessage):
        """Handle kill switch commands."""
        payload = msg.payload
        level = payload.get("level", "")
        target = payload.get("target", "")

        if level == KillSwitchLevel.GLOBAL.value:
            self._killed = True
            logger.critical(f"🛑 [{self.account_id}] GLOBAL KILL — stopping all new executions")
        elif level == KillSwitchLevel.ACCOUNT.value and target == self.account_id:
            self._killed = True
            logger.critical(f"🛑 [{self.account_id}] ACCOUNT KILL — stopping new executions")

    # ═══════════════════════════════════════════════════════════
    #  STATS
    # ═══════════════════════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "process": self.process_name,
            "login": self.config.login,
            "connected": self._connected,
            "killed": self._killed,
            "daily_trades": self._daily_trades,
            "daily_pnl": self._daily_pnl,
            "uptime": self.uptime,
        }


# ════════════════════════════════════════════════════════════════
#  STANDALONE PROCESS ENTRY POINT
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    from zohra.config.settings import ACCOUNT_CONFIGS, LOG_DIR

    parser = argparse.ArgumentParser(description="ZOHRA Isolated Account Worker")
    parser.add_argument("--account-id", required=True, help="Account ID (e.g. account_01, account_02, account_03)")
    args = parser.parse_args()

    matching = [c for c in ACCOUNT_CONFIGS if c.account_id == args.account_id or str(c.login) == args.account_id]
    if not matching:
        print(f"❌ Error: Account ID '{args.account_id}' not found in configuration.")
        sys.exit(1)

    config = matching[0]

    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"worker_{config.account_id}.log")
    logging.basicConfig(
        level=logging.INFO,
        format=f"[%(asctime)s UTC] [%(levelname)s] [{config.account_id}] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ]
    )

    worker = AccountWorker(config)

    async def run():
        if not worker.start():
            logger.error(f"Failed to start AccountWorker for {config.account_id}")
            return
        try:
            await worker.run_loop()
        finally:
            worker.stop()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        worker.stop()
        print(f"AccountWorker {config.account_id} stopped.")
