"""
╔══════════════════════════════════════════════════════════════════════╗
║                    ZOHRA — CAPITAL SCALING ENGINE                    ║
║          Layer 3 Dynamic Position Management & Scaling               ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from zohra.brokers.manager import broker_manager as mt5_broker
from zohra.core.risk_guardian import risk_guardian
from zohra.config.settings import METAL_SYMBOLS
from zohra.db.schema import db

logger = logging.getLogger("zohra.scaling")

class CapitalScalingSystem:
    """
    Capital Scaling System:
    - Scales up approved positions dynamically.
    - Curtails or closes rejected probe positions immediately.
    """
    async def apply_scaling(self, probe_trade: dict, ruling: dict):
        """
        Takes an active probe trade and the validation ruling.
        Executes scale-up deals, risk reductions, or position closures.
        """
        symbol = probe_trade["symbol"]
        ticket = probe_trade["mt5_ticket"]
        direction = probe_trade["direction"]
        action = ruling["action"]
        grade = ruling["grade"]

        logger.info(f"⚙️  [Scaling] Applying ruling for active probe #{ticket}: {action} (Grade {grade})")

        # 1. Close immediately if rejected
        if action == "REJECT":
            logger.warning(f"🚨 [Scaling] Probe position #{ticket} REJECTED by Committee. Closing immediately...")
            try:
                from zohra.learning.trade_forensics import trade_forensics
                trade_forensics.log_rejection(
                    symbol=symbol, direction=direction, strategy=probe_trade.get("strategy", "Unknown"),
                    confidence_score=float(ruling.get("final_score", 0)),
                    rejection_reason=f"Validation Committee Veto: {ruling.get('chairman_summary', 'Rejected')}",
                    rejection_category="COMMITTEE", regime=probe_trade.get("regime", ""),
                    session=probe_trade.get("session", ""), entry_price=probe_trade.get("entry_price", 0),
                    stop_loss=probe_trade.get("stop_loss", 0), take_profit=probe_trade.get("take_profit", 0)
                )
                trade_forensics.log_decision(
                    symbol=symbol, direction=direction, strategy=probe_trade.get("strategy", "Unknown"),
                    decision="VETOED", confidence_score=float(ruling.get("final_score", 0)),
                    regime=probe_trade.get("regime", ""), session=probe_trade.get("session", ""),
                    entry_price=probe_trade.get("entry_price", 0), stop_loss=probe_trade.get("stop_loss", 0),
                    take_profit=probe_trade.get("take_profit", 0), rejection_reason=f"Validation Committee Veto: {ruling.get('chairman_summary', 'Rejected')}"
                )
            except Exception as e:
                logger.error(f"Error logging validation committee rejection in forensics: {e}")
            
            # Retrieve open volume details
            positions = await asyncio.to_thread(mt5_broker.get_open_positions)
            matching = next((p for p in positions if p["ticket"] == ticket), None)
            
            if matching:
                lots = matching["lots"]
                close_res = await asyncio.to_thread(
                    mt5_broker.close_position, 
                    ticket, symbol, lots, direction
                )
                if close_res.get("success"):
                    logger.info(f"✅ [Scaling] Closed rejected probe #{ticket} successfully.")
                    try:
                        db.log_system("INFO", f"Closed rejected probe position #{ticket} on {symbol}", "Scaling")
                    except Exception:
                        pass
                else:
                    logger.error(f"❌ [Scaling] Failed to close rejected probe #{ticket}: {close_res.get('comment')}")
            return

        # 2. Reduce risk if speculative (Grade C)
        if action == "REDUCE":
            logger.warning(f"🛡️  [Scaling] Probe position #{ticket} graded C (Speculative). Moving stop loss to Breakeven.")
            # Move SL to breakeven (entry price) to eliminate downside risk
            modify_res = await asyncio.to_thread(
                mt5_broker.modify_trade,
                ticket,
                new_sl=probe_trade["entry_price"]
            )
            if modify_res.get("success"):
                logger.info(f"✅ [Scaling] Successfully moved SL to Breakeven for probe #{ticket}.")
            else:
                logger.error(f"❌ [Scaling] Failed to modify SL to Breakeven for probe #{ticket}: {modify_res.get('comment')}")
            return

        # 3. Maintain if Grade B
        if action == "MAINTAIN":
            logger.info(f"✊ [Scaling] Probe position #{ticket} graded B. Maintaining current probe size ({probe_trade['position_size_lots']} lots).")
            return

        # 4. Scale up if Grade A or A+
        scale_lots = 0.0
        if action == "SCALE_MAX": # Grade A+ (adds 0.02)
            scale_lots = 0.20 if symbol in METAL_SYMBOLS else 0.02
        elif action == "SCALE_NORMAL": # Grade A (adds 0.01)
            scale_lots = 0.10 if symbol in METAL_SYMBOLS else 0.01

        if scale_lots > 0:
            # ─── ATR Price Deviation Guard ───
            # Block scale-up if current price has moved > 1 ATR from probe entry.
            # This prevents chasing extended moves and limits adverse fill risk.
            atr_value = await self._calculate_atr(symbol, period=14)
            if atr_value and atr_value > 0:
                entry_price = float(probe_trade.get("entry_price", 0))
                price_dict = await asyncio.to_thread(mt5_broker.get_current_price, symbol)
                current_price = price_dict.get("mid") or price_dict.get("bid", 0.0) if price_dict else 0.0
                if entry_price > 0 and current_price > 0:
                    price_deviation = abs(current_price - entry_price)
                    if price_deviation > atr_value:
                        logger.warning(
                            f"⏭️  [Scaling] ATR deviation guard triggered for #{ticket}. "
                            f"Deviation={price_deviation:.5f} > 1×ATR={atr_value:.5f}. Skipping scale-up."
                        )
                        try:
                            db.log_system(
                                "WARNING",
                                f"Scale-up blocked: price deviation {price_deviation:.5f} > ATR {atr_value:.5f} for #{ticket}",
                                "Scaling"
                            )
                        except Exception:
                            pass
                        return
                    else:
                        logger.info(f"✅ [Scaling] ATR check passed. Deviation={price_deviation:.5f} <= ATR={atr_value:.5f}.")

            # Check Risk Guardian again before executing scale-up order
            # This now enforces both per-symbol (MAX_SCALE_UP_TICKETS_PER_SYMBOL)
            # and global (MAX_OPEN_POSITIONS) limits
            is_safe, reason = risk_guardian.evaluate_execution_safety(symbol, direction, scale_lots)
            if not is_safe:
                logger.warning(f"⏭️  [Scaling] Risk Guardian blocked scale-up order: {reason}. Maintaining base probe.")
                return

            # Resolve broker for this symbol
            from zohra.core.symbol_manager import symbol_manager
            sym_params = symbol_manager.get_symbol_params(symbol)
            broker = sym_params.get("broker") if sym_params else None

            # NOTE: MT5 does not support modifying volume on open positions.
            # Scale-ups must open new tickets, but are now strictly gated by
            # Risk Guardian limits (max 3 per symbol, max 5 total).
            order = {
                "symbol": symbol,
                "direction": direction,
                "volume_lots": scale_lots,
                "stop_loss": probe_trade["stop_loss"],
                "take_profit": probe_trade["take_profit"],
                "comment": f"ZSC_SCALE_{grade}",
                "magic": probe_trade["magic"]
            }

            logger.info(f"🚀 [Scaling] Scaling UP position: Adding {scale_lots} lots to {symbol} (Probe Ticket #{ticket})")
            
            # Execute scale-up deal order
            exec_res = await asyncio.to_thread(mt5_broker.open_position, order, broker=broker)
            if exec_res.get("success"):
                new_ticket = exec_res["mt5_ticket"]
                fill_price = exec_res["fill_price"]
                probe_trade["scaling_lots_added"] = scale_lots
                logger.info(f"✅ [Scaling] Scale-up filled successfully! Added Ticket #{new_ticket} at {fill_price}.")
            else:
                logger.error(f"❌ [Scaling] Scale-up execution failed for {symbol}: {exec_res.get('comment')}")
    # ─── ATR Calculation Helper ───
    async def _calculate_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """
        Calculate Average True Range (ATR) for a symbol using M15 candle data.
        Uses pure-Python arithmetic — no numpy dependency.
        Returns ATR value or None on failure.
        """
        try:
            df = await asyncio.to_thread(mt5_broker.get_ohlcv, symbol, "M15", period + 1)
            if df is None or len(df) < period + 1:
                logger.warning(f"[Scaling ATR] Insufficient candle data for {symbol}. Got {len(df) if df is not None else 0} bars.")
                return None

            rates = df.to_dict('records')
            true_ranges: List[float] = []
            for i in range(1, len(rates)):
                high = float(rates[i].get("high", 0))
                low = float(rates[i].get("low", 0))
                prev_close = float(rates[i - 1].get("close", 0))
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                true_ranges.append(tr)

            if len(true_ranges) < period:
                return None

            atr = sum(true_ranges[-period:]) / period
            logger.debug(f"[Scaling ATR] {symbol} ATR({period}) = {atr:.5f}")
            return atr
        except Exception as e:
            logger.error(f"[Scaling ATR] Error computing ATR for {symbol}: {e}")
            return None

# Singleton
scaling_system = CapitalScalingSystem()
