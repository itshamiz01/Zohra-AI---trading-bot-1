"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — SCOUT SCALPING ENGINE                      ║
║          Layer 1 Low-Latency Execution & Probe Trades                ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import asyncio
import time
import uuid
from typing import Dict, Any, Optional
from zohra.brokers.manager import broker_manager as mt5_broker
from zohra.core.risk_guardian import risk_guardian
from zohra.config.settings import MAGIC_SCALP, MAGIC_SMC, STATE

logger = logging.getLogger("zohra.scout")

class ScoutEngine:
    """
    Scout Engine (Layer 1):
    - Fast, low-latency, continuous execution pipeline.
    - Places small probe positions (0.01/0.10 lots) to test structures without committee delays.
    """
    def __init__(self, brain=None):
        self.brain = brain
        self.probe_lot_forex = 0.01
        self.probe_lot_metal = 0.01  # Reduced from 0.10 for $200 account safety

    async def evaluate_and_execute_probe(self, symbol: str, signal_data: dict) -> Optional[dict]:
        """
        Main entry point for Scout.
        Checks Risk Guardian, executes the deal, and schedules validation committee.
        """
        # 0. Hard Symbol Guard check — Strictly Gold (XAUUSD) Only
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading disabled for {symbol}. Gold-only mode is active.")
            return None

        direction = signal_data["direction"]
        strategy = signal_data["strategy"]
        entry_price = signal_data.get("entry_price") or signal_data.get("entry")
        sl = signal_data.get("stop_loss") or signal_data.get("stop")
        tp = signal_data.get("take_profit") or signal_data.get("tp2") or signal_data.get("tp1")

        if not (entry_price and sl and tp):
            logger.warning(f"🔍 [Scout] Signal for {symbol} missing entry/SL/TP parameters. Skipping.")
            return None

        # Determine probe size with metal volatility adjustment
        from zohra.config.settings import METAL_SYMBOLS, METAL_LOT_MULTIPLIER
        is_metal = symbol in METAL_SYMBOLS
        if is_metal:
            lots = max(round(self.probe_lot_metal * METAL_LOT_MULTIPLIER, 2), 0.01)
        else:
            lots = self.probe_lot_forex

        # 1. Supreme Risk Guardian Evaluation
        is_safe, reason = risk_guardian.evaluate_execution_safety(symbol, direction, lots, is_probe=True)
        if not is_safe:
            logger.warning(f"⏭️  [Scout] Risk Guardian vetoed probe for {symbol}: {reason}")
            try:
                from zohra.learning.trade_forensics import trade_forensics
                trade_forensics.log_rejection(
                    symbol=symbol, direction=direction, strategy=strategy,
                    confidence_score=signal_data.get("confidence_score", 0),
                    rejection_reason=f"Risk Guardian Scout Veto: {reason}",
                    rejection_category="RISK", regime=signal_data.get("regime", ""),
                    session=signal_data.get("session", ""), entry_price=entry_price,
                    stop_loss=sl, take_profit=tp,
                    scores=signal_data.get("scores_breakdown"), vol_ratio=signal_data.get("vol_ratio", 1.0)
                )
            except Exception as e:
                logger.error(f"Error logging Scout Risk Guardian veto in forensics: {e}")
            return None

        # Resolve symbol broker mapping
        from zohra.core.symbol_manager import symbol_manager
        sym_params = symbol_manager.get_symbol_params(symbol)
        broker = sym_params.get("broker") if sym_params else None

        # 2. Portfolio Risk Coordinator & Cross-Bot Duplicate Check
        from zohra.core.portfolio_risk_coordinator import portfolio_risk_coordinator
        from zohra.core.strategy_fingerprint import build_strategy_fingerprint, StrategyFingerprint
        from zohra.config.settings import BOT_ID, BOT_NAME, BOT_ROLE

        fp = signal_data.get("fingerprint")
        if not fp or not isinstance(fp, StrategyFingerprint):
            fp = build_strategy_fingerprint(
                bot_id=BOT_ID,
                bot_name=BOT_NAME,
                bot_role=BOT_ROLE,
                signal_data=signal_data,
                regime_report=None,
                symbol=symbol
            )

        approval = portfolio_risk_coordinator.evaluate_execution_approval(fp, requested_lots=lots)
        if not approval.approved:
            logger.warning(f"🚨 [Scout] Portfolio Risk Coordinator VETO for {symbol}: {approval.rejection_reason}")
            try:
                from zohra.learning.trade_forensics import trade_forensics
                trade_forensics.log_rejection(
                    symbol=symbol, direction=direction, strategy=strategy,
                    confidence_score=signal_data.get("confidence_score", 0),
                    rejection_reason=f"Portfolio Risk Veto: {approval.rejection_reason}",
                    rejection_category="PORTFOLIO_RISK", regime=signal_data.get("regime", ""),
                    session=signal_data.get("session", ""), entry_price=entry_price,
                    stop_loss=sl, take_profit=tp
                )
            except Exception:
                pass
            return None

        if approval.adjusted_lot_multiplier < 1.0:
            lots = max(round(lots * approval.adjusted_lot_multiplier, 2), 0.01)
            logger.info(f"⚖️ [Scout] Position size adjusted to {lots} lots by Portfolio Risk Coordinator.")

        # 3. Package execution request
        magic = MAGIC_SCALP if "scalp" in strategy.lower() else MAGIC_SMC
        order = {
            "symbol": symbol,
            "direction": direction,
            "volume_lots": lots,
            "stop_loss": sl,
            "take_profit": tp,
            "comment": f"ZSC_PROBE_{strategy[:5]}",
            "magic": magic
        }

        logger.info(f"🏹 [Scout] Triggering PROBE position entry: {direction} {symbol} ({lots} lots) on broker={broker}")

        # 4. Direct Deal Execution
        t_start = time.perf_counter()
        exec_result = await asyncio.to_thread(mt5_broker.open_position, order, broker=broker)
        exec_latency = (time.perf_counter() - t_start) * 1000.0

        if exec_result.get("success"):
            ticket = exec_result["mt5_ticket"]
            fill_price = exec_result["fill_price"]
            logger.info(f"🎯 [Scout] Probe filled successfully! Ticket #{ticket} at {fill_price} | Latency={exec_latency:.1f}ms")

            # Register in central fleet risk state
            portfolio_risk_coordinator.register_open_position(
                bot_id=BOT_ID,
                ticket=ticket,
                symbol=symbol,
                direction=direction,
                lots=lots,
                strategy=strategy,
                entry_price=fill_price
            )

            # 5. Formulate the active probe position dictionary
            probe_trade = {
                "trade_id": f"ZHR_PROBE_{symbol}_{uuid.uuid4().hex[:8].upper()}",
                "mt5_ticket": ticket,
                "symbol": symbol,
                "direction": direction,
                "entry_price": fill_price,
                "stop_loss": sl,
                "take_profit": tp,
                "position_size_lots": lots,
                "strategy": strategy,
                "magic": magic,
                "scout_latency_ms": exec_latency,
                "entry_time": time.time(),
                "has_been_validated": False,
                "scaling_lots_added": 0.0,
                "broker": broker or "mt5"
            }

            # 6. Spawn background task to run committee validation
            if self.brain:
                self.brain.loop.create_task(self._dispatch_validation(probe_trade, signal_data))
            else:
                asyncio.create_task(self._dispatch_validation(probe_trade, signal_data))

            return probe_trade
        else:
            logger.error(f"❌ [Scout] Probe order execution failed for {symbol}: {exec_result.get('comment')}")
            return None

    async def _dispatch_validation(self, probe_trade: dict, signal_data: dict):
        """Asynchronously triggers the validation committee to audit the probe trade."""
        # Wait a short moment (e.g. 500ms) for execution state tracking to settle
        await asyncio.sleep(0.5)
        
        # Access validation committee dynamically to prevent import loops
        try:
            from zohra.core.validation_committee import validation_committee
            from zohra.core.scaling_system import scaling_system
            
            logger.info(f"⚖️  [Scout] Handing off active probe #{probe_trade['mt5_ticket']} to Validation Committee...")
            
            # Execute validation debate
            ruling = await validation_committee.validate_probe(probe_trade, signal_data)
            
            # Execute scaling system actions based on ruling
            await scaling_system.apply_scaling(probe_trade, ruling)
            
        except Exception as e:
            logger.error(f"Error during async committee validation: {e}")

# Singleton
scout_engine = ScoutEngine()
