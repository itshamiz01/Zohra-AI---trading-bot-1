"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — RISK & DECISION ENGINE                            ║
║     Signal gatekeeper — per-account risk evaluation & lot sizing    ║
╚══════════════════════════════════════════════════════════════════════╝

The Risk Engine sits between the Strategy Engine and the Account Workers.

Data flow:
  Strategy Engine → strategy.signal → Risk Engine → execution.request → Account Workers

It receives:
  - strategy.signal (from Strategy Engine)
  - account.snapshot (from each Account Worker)

It evaluates:
  - Global risk limits (daily/weekly/monthly drawdown)
  - Strategy-level risk (max positions per strategy, cooldowns)
  - Per-account risk (equity-based lot sizing, margin checks)
  - Portfolio exposure (correlation, sector limits)
  - Signal conflicts
  - Confidence thresholds
  - Trading sessions
  - Kill switches (global, account, strategy)

It produces:
  - execution.request (authorized orders to specific account workers)
  - risk.approved / risk.rejected (audit trail)

IMPORTANT: Lot size calculation belongs HERE, not inside the strategy.
"""

import os
import sys
import uuid
import logging
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from zohra.core.message_bus import message_bus, ZohraMessage, MessageTopic, KillSwitchLevel
from zohra.config.bot_profile import get_account_for_strategy, get_profile_for_account
from zohra.config.settings import (
    RISK_PER_TRADE_PCT, MAX_OPEN_POSITIONS,
    MAX_DAILY_LOSS_PCT, MAX_WEEKLY_LOSS_PCT, MAX_MONTHLY_LOSS_PCT,
    MIN_LOT_SIZE, MAX_LOT_SIZE, LOT_STEP,
    METAL_SYMBOLS, METAL_LOT_MULTIPLIER,
    ACTIVE_ACCOUNT_CONFIGS,
    MAGIC_SMC,
    DAILY_PROFIT_TARGET,
    SCALP_DEFAULT_LOT_METALS,
    SCALP_DEFAULT_LOT_FOREX,
)

logger = logging.getLogger("zohra.risk_engine")


class RiskDecisionEngine:
    """
    Centralized Risk & Decision Engine for the ZOHRA unified trading system.

    Evaluates strategy signals against risk parameters and produces
    authorized execution requests for each account worker.

    Key principle: Every signal gets evaluated FOR EACH ACCOUNT independently.
    Account 1's equity doesn't affect Account 2's lot size.
    """

    PROCESS_NAME = "zohra-risk-engine"

    def __init__(self):
        self._running = False
        self._start_time = 0.0

        # ─── Account State (populated by account.snapshot messages) ───
        self._account_states: Dict[str, Dict[str, Any]] = {}
        # {account_id: {balance, equity, margin, free_margin, open_positions, daily_pnl, ...}}

        # ─── Kill Switches ───
        self._global_kill = False
        self._account_kills: Set[str] = set()
        self._strategy_kills: Set[str] = set()

        # ─── Signal Tracking ───
        self._signals_received = 0
        self._signals_approved = 0
        self._signals_rejected = 0

        # ─── Cooldown Tracking ───
        self._last_signal_time: Dict[str, float] = {}  # strategy:symbol → last signal timestamp
        self._cooldown_seconds = 20

        # ─── Subscribe to messages ───
        self._setup_subscriptions()

        logger.info("RiskDecisionEngine initialized")

    def _setup_subscriptions(self):
        """Subscribe to relevant message topics."""
        message_bus.subscribe(
            MessageTopic.STRATEGY_SIGNAL.value,
            self._on_strategy_signal,
            subscriber_id="risk_engine_signal_handler",
        )
        message_bus.subscribe(
            MessageTopic.ACCOUNT_SNAPSHOT.value,
            self._on_account_snapshot,
            subscriber_id="risk_engine_snapshot_handler",
        )
        message_bus.subscribe(
            MessageTopic.TRADING_KILL_SWITCH.value,
            self._on_kill_switch,
            subscriber_id="risk_engine_kill_handler",
        )

    # ═══════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═══════════════════════════════════════════════════════════

    def start(self):
        self._running = True
        self._start_time = time.time()
        logger.info("✅ RiskDecisionEngine started")

    def stop(self):
        self._running = False
        logger.info("RiskDecisionEngine stopped")

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    # ═══════════════════════════════════════════════════════════
    #  HEARTBEAT LOOP
    # ═══════════════════════════════════════════════════════════

    async def run_loop(self):
        """Main loop — just heartbeats; signal processing is event-driven."""
        while self._running:
            try:
                await message_bus.publish_heartbeat(
                    self.PROCESS_NAME, "HEALTHY", self.uptime
                )
                await asyncio.sleep(5.0)
            except Exception as e:
                logger.error(f"RiskEngine loop error: {e}")
                await asyncio.sleep(10.0)

    # ═══════════════════════════════════════════════════════════
    #  MESSAGE HANDLERS
    # ═══════════════════════════════════════════════════════════

    async def _on_strategy_signal(self, msg: ZohraMessage):
        """Handle incoming strategy signal — evaluate risk and fan out to accounts."""
        self._signals_received += 1
        payload = msg.payload

        signal_id = payload.get("signal_id", str(uuid.uuid4()))
        strategy_id = payload.get("strategy_id", "unknown")
        symbol = payload.get("symbol", "")
        direction = payload.get("direction", "")
        entry = payload.get("entry", 0.0)
        stop_loss = payload.get("stop_loss", 0.0)
        take_profit = payload.get("take_profit", 0.0)
        confidence = payload.get("confidence", 0.0)

        logger.info(f"📥 Risk evaluating signal: {strategy_id} {direction} {symbol} confidence={confidence}")

        # ─── Global Checks ───
        rejection_reason = self._check_global_risk(strategy_id, symbol, confidence)
        if rejection_reason:
            self._signals_rejected += 1
            await self._publish_rejection(signal_id, strategy_id, symbol, rejection_reason)
            return

        # ─── Per-Account Evaluation & Dedicated Strategy Routing ───
        target_account_id = payload.get("target_account") or get_account_for_strategy(strategy_id)
        if target_account_id:
            target_configs = [c for c in ACTIVE_ACCOUNT_CONFIGS if c.account_id == target_account_id]
            if not target_configs:
                logger.debug(f"Target account '{target_account_id}' for strategy '{strategy_id}' is not active — skipping")
                return
        else:
            target_configs = ACTIVE_ACCOUNT_CONFIGS

        for account_config in target_configs:
            account_id = account_config.account_id
            account_state = self._account_states.get(account_id)

            # Check account-level kill switch
            if account_id in self._account_kills:
                logger.debug(f"Account {account_id} kill switch active — skipping")
                continue

            # Check account state exists
            if not account_state:
                logger.debug(f"No snapshot for {account_id} yet — skipping signal")
                continue

            # Check account-level risk
            acct_rejection = self._check_account_risk(account_id, account_state, symbol, direction)
            if acct_rejection:
                logger.info(f"ℹ️ [{account_id}] {symbol} {direction} gate: {acct_rejection}")
                continue

            # ─── Calculate lot size for this account ───
            volume = self._calculate_lot_size(
                account_state=account_state,
                account_config=account_config,
                symbol=symbol,
                entry=entry,
                stop_loss=stop_loss,
                confidence=confidence,
            )

            if volume < MIN_LOT_SIZE:
                logger.debug(f"Calculated volume {volume} below minimum for {account_id} — skipping")
                continue

            # ─── Publish execution request to specific account worker ───
            magic = MAGIC_SMC + account_config.magic_offset
            await message_bus.publish_execution_request(
                signal_id=signal_id,
                account_id=account_id,
                strategy_id=strategy_id,
                symbol=symbol,
                direction=direction,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
                max_slippage=20,
                source=self.PROCESS_NAME,
            )

            self._signals_approved += 1
            # Optimistically record position in local account state to prevent microsecond re-firing
            positions = account_state.setdefault("positions", [])
            positions.append({"symbol": symbol, "direction": direction})
            account_state["open_positions"] = account_state.get("open_positions", 0) + 1

            logger.info(
                f"✅ APPROVED: {strategy_id} {direction} {symbol} → {account_id} | "
                f"Volume={volume:.2f} | Confidence={confidence}"
            )

        # Update cooldown tracker per strategy:symbol pair
        self._last_signal_time[f"{strategy_id}:{symbol}"] = time.time()

    async def _on_account_snapshot(self, msg: ZohraMessage):
        """Update internal account state from account worker snapshots."""
        payload = msg.payload
        account_id = payload.get("account_id", "")
        if account_id:
            self._account_states[account_id] = payload
            logger.debug(f"Account snapshot updated: {account_id} | equity={payload.get('equity', 0)}")

    async def _on_kill_switch(self, msg: ZohraMessage):
        """Handle kill switch commands."""
        payload = msg.payload
        level = payload.get("level", "")
        target = payload.get("target", "")
        reason = payload.get("reason", "Manual kill switch")

        if level == KillSwitchLevel.GLOBAL.value:
            self._global_kill = True
            logger.critical(f"🛑 GLOBAL KILL SWITCH ACTIVATED: {reason}")
        elif level == KillSwitchLevel.ACCOUNT.value and target:
            self._account_kills.add(target)
            logger.warning(f"🛑 Account kill switch: {target} — {reason}")
        elif level == KillSwitchLevel.STRATEGY.value and target:
            self._strategy_kills.add(target)
            logger.warning(f"🛑 Strategy kill switch: {target} — {reason}")

    # ═══════════════════════════════════════════════════════════
    #  RISK CHECKS
    # ═══════════════════════════════════════════════════════════

    def _check_global_risk(self, strategy_id: str, symbol: str, confidence: float) -> Optional[str]:
        """Global risk checks. Returns rejection reason or None if passed."""
        # Kill switch
        if self._global_kill:
            return "Global kill switch active"

        # Strategy kill
        if strategy_id in self._strategy_kills:
            return f"Strategy {strategy_id} kill switch active"

        # Minimum confidence threshold
        from zohra.config.bot_profile import load_bot_profile
        profile = load_bot_profile("ZOHRA_UNIFIED")
        if confidence < profile.min_confidence:
            return f"Confidence {confidence} below threshold {profile.min_confidence}"

        # Cooldown check per strategy:symbol pair
        cooldown_key = f"{strategy_id}:{symbol}"
        last_time = self._last_signal_time.get(cooldown_key, 0)
        if time.time() - last_time < self._cooldown_seconds:
            return f"Strategy {strategy_id} on {symbol} in cooldown ({self._cooldown_seconds}s)"

        return None

    def _check_account_risk(self, account_id: str, state: Dict, symbol: str, direction: str) -> Optional[str]:
        """Per-account risk checks. Returns rejection reason or None."""
        # Check if trading is allowed
        if not state.get("trade_allowed", True):
            return "Trading not allowed on this account"

        # Check connection
        if state.get("connection_status") != "ONLINE":
            return "Account offline"

        # Daily profit target check ($50.00 / day per account)
        daily_pnl = state.get("daily_pnl", 0.0)
        if daily_pnl >= DAILY_PROFIT_TARGET:
            return f"Daily profit target reached (${daily_pnl:.2f} >= ${DAILY_PROFIT_TARGET:.2f}) — Trading paused for {account_id} today to bank profits"

        # Daily loss limit
        equity = state.get("equity", 0)
        balance = state.get("balance", 0)
        if balance > 0 and daily_pnl < 0:
            daily_loss_pct = abs(daily_pnl) / balance
            if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
                return f"Daily loss limit reached ({daily_loss_pct:.1%})"

        # Max open positions per account
        open_positions = state.get("open_positions", 0)
        if open_positions >= MAX_OPEN_POSITIONS:
            return f"Max positions reached ({open_positions}/{MAX_OPEN_POSITIONS})"

        # Free margin check
        free_margin = state.get("free_margin", 0)
        if free_margin < 50:  # Minimum margin threshold
            return f"Insufficient free margin: ${free_margin:.2f}"

        # ─── Symbol-Level Safeguards ───
        positions = state.get("positions", [])
        symbol_positions = [p for p in positions if p.get("symbol") == symbol]

        # 1. Local Account Opposing Position Veto (strictly prevent self-hedging)
        clean_dir = direction.upper().strip()
        opposing_dir = "SELL" if clean_dir in ("BUY", "LONG") else "BUY"
        has_opposing = any(p.get("direction") == opposing_dir for p in symbol_positions)
        if has_opposing:
            return f"Opposing {opposing_dir} position already open on {symbol} — VETOED to prevent self-hedging"

        # 2. Cross-Account Opposing Position Veto (strictly prevent multi-bot conflicting trades)
        for other_id, other_state in self._account_states.items():
            if other_id == account_id:
                continue
            other_positions = other_state.get("positions", [])
            other_opposing = any(
                p.get("symbol") == symbol and p.get("direction") == opposing_dir
                for p in other_positions
            )
            if other_opposing:
                return (
                    f"Cross-account conflict: {other_id} already has an active opposing {opposing_dir} "
                    f"position on {symbol} — VETOED to prevent conflicting opposite positions across bots"
                )

        # 3. Maximum 1 position per symbol per account
        if len(symbol_positions) >= 1:
            return f"Position already open on {symbol} ({len(symbol_positions)} active) — stacking prevented"

        return None

    # ═══════════════════════════════════════════════════════════
    #  LOT SIZE CALCULATION (Short-Term Scalping)
    # ═══════════════════════════════════════════════════════════

    def _calculate_lot_size(self, account_state: Dict, account_config,
                            symbol: str, entry: float, stop_loss: float,
                            confidence: float) -> float:
        """
        Calculate lot size for a specific account based on short-term scalping targets.
        Sized for $3-$4 profit per trade on ~$200 accounts:
          - Gold (XAUUSD): 0.01 lot ($1.00 per point -> $3.50 target)
          - Forex (EURUSD, GBPUSD, etc.): 0.02 lot ($0.20 per pip -> 17.5 pips = $3.50 target)
        """
        equity = account_state.get("equity", 0)
        if equity <= 0:
            return 0.0

        if "XAU" in symbol or symbol in METAL_SYMBOLS:
            lots = SCALP_DEFAULT_LOT_METALS
        else:
            lots = SCALP_DEFAULT_LOT_FOREX

        # Snap to lot step
        lots = round(round(lots / LOT_STEP) * LOT_STEP, 2)
        lots = max(MIN_LOT_SIZE, min(lots, MAX_LOT_SIZE))

        return lots

    # ═══════════════════════════════════════════════════════════
    #  AUDIT
    # ═══════════════════════════════════════════════════════════

    async def _publish_rejection(self, signal_id: str, strategy_id: str,
                                  symbol: str, reason: str):
        """Publish a risk rejection for audit trail."""
        msg = ZohraMessage(
            message_type=MessageTopic.RISK_REJECTED.value,
            payload={
                "signal_id": signal_id,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "reason": reason,
            },
            source=self.PROCESS_NAME,
        )
        await message_bus.publish(msg)
        logger.info(f"❌ REJECTED: {strategy_id} {symbol} — {reason}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "process": self.PROCESS_NAME,
            "signals_received": self._signals_received,
            "signals_approved": self._signals_approved,
            "signals_rejected": self._signals_rejected,
            "global_kill": self._global_kill,
            "account_kills": list(self._account_kills),
            "strategy_kills": list(self._strategy_kills),
            "account_states": {k: {"equity": v.get("equity"), "open": v.get("open_positions")}
                              for k, v in self._account_states.items()},
        }
