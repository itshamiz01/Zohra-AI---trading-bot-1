"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — PAPER TRADING ENGINE                           ║
║     Real-Time Virtual Account Environment & Execution Simulation    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from zohra.event_bus import event_bus
from zohra.config.settings import settings

logger = logging.getLogger("zohra.validation.paper")


class PaperTradingEngine:
    """
    Virtual broker emulator running in-memory or via SQL logs.
    Simulates real-time order processing, partial fills, commissions, and spreads.
    """

    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        
        self.open_positions: Dict[str, Dict] = {}  # ticket_id → position
        self.order_queue: List[Dict] = []
        self.trade_journal: List[Dict] = []

        # Cost parameters
        self.slippage_pips = getattr(settings, "VALIDATION_SLIPPAGE_PIPS", 0.5)
        self.latency_ms = getattr(settings, "VALIDATION_LATENCY_MS", 150)
        self.commission_per_lot = getattr(settings, "VALIDATION_COMMISSION_USD_PER_LOT", 3.50)

    def reset_account(self, balance: float = 100000.0):
        self.initial_balance = balance
        self.balance = balance
        self.equity = balance
        self.open_positions = {}
        self.order_queue = []
        self.trade_journal = []

    def get_portfolio_status(self) -> Dict[str, Any]:
        """Compute virtual equity, margin, and PnL metrics."""
        floating_pnl = 0.0
        for pos in self.open_positions.values():
            floating_pnl += pos.get("profit", 0.0)
            
        self.equity = self.balance + floating_pnl
        margin_used = sum(p.get("margin", 0.0) for p in self.open_positions.values())
        
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "margin_used": round(margin_used, 2),
            "free_margin": round(self.equity - margin_used, 2),
            "open_positions_count": len(self.open_positions),
            "floating_pnl": round(floating_pnl, 2),
            "positions": list(self.open_positions.values()),
        }

    # ─── Order Processing ─────────────────────────────────────

    def place_order(self, symbol: str, direction: str, lots: float, 
                    stop_loss: float = 0.0, take_profit: float = 0.0,
                    price: float = 0.0) -> Dict[str, Any]:
        """Simulates placing an order with latency and slippage emulation."""
        ticket = str(uuid.uuid4())[:8]
        
        # Sizing and Margin check (approximate $1000 margin per Forex lot)
        required_margin = lots * 1000.0
        if self.equity - required_margin < 0:
            return {"status": "error", "reason": "Insufficient margin"}

        # Simulate execution price
        pip = 0.01 if "JPY" in symbol or "XAU" in symbol else 0.0001
        slippage = self.slippage_pips * pip
        commission = lots * self.commission_per_lot * 2  # round trip

        if price == 0.0:
            # Market order (fetch current price approximation)
            try:
                from zohra.brokers.manager import broker_manager
                tick = broker_manager.get_tick(symbol)
                base_price = tick["ask"] if direction == "LONG" else tick["bid"]
            except Exception:
                base_price = 1.0850 # Fallback

            if direction == "LONG":
                exec_price = base_price + slippage
            else:
                exec_price = base_price - slippage
        else:
            # Pending/Limit execution price
            exec_price = price

        pos = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "entry_price": exec_price,
            "current_price": exec_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "margin": required_margin,
            "profit": 0.0,
            "commission": commission,
            "open_time": datetime.utcnow().isoformat(),
        }

        self.open_positions[ticket] = pos
        logger.info(f"🟢 [Paper Trading] Filled position: {symbol} {direction} {lots}L @ {exec_price:.5f} | Ticket: {ticket}")

        # Emit update event for AI learning loop
        self._emit_update_event("paper.fill", pos)

        return {"status": "success", "ticket": ticket, "position": pos}

    def close_position(self, ticket: int, price: float = 0.0) -> Dict[str, Any]:
        """Realizes profit/loss on a position."""
        t_str = str(ticket)
        if t_str not in self.open_positions:
            return {"status": "error", "reason": "Position not found"}

        pos = self.open_positions[t_str]
        
        if price == 0.0:
            try:
                from zohra.brokers.manager import broker_manager
                tick = broker_manager.get_tick(pos["symbol"])
                price = tick["bid"] if pos["direction"] == "LONG" else tick["ask"]
            except Exception:
                price = pos["entry_price"]  # Fallback

        dir_mult = 1 if pos["direction"] == "LONG" else -1
        pip = 0.01 if "JPY" in pos["symbol"] or "XAU" in pos["symbol"] else 0.0001
        
        pips_gain = (price - pos["entry_price"]) * dir_mult
        contract_size = 100000.0 if "XAU" not in pos["symbol"] else 100.0
        gross_pnl = pips_gain * contract_size * pos["lots"]
        net_pnl = gross_pnl - pos["commission"]

        self.balance += net_pnl
        del self.open_positions[t_str]

        closed_record = {
            **pos,
            "exit_price": price,
            "close_time": datetime.utcnow().isoformat(),
            "pnl": round(net_pnl, 2),
            "pips": round(pips_gain / pip, 1),
        }
        self.trade_journal.append(closed_record)
        logger.info(f"🔴 [Paper Trading] Closed position: {pos['symbol']} Ticket: {ticket} | PnL: ${net_pnl:.2f}")

        # Emit close event
        self._emit_update_event("paper.close", closed_record)

        return {"status": "success", "closed_record": closed_record}

    # ─── Live Market Tracker ──────────────────────────────────

    def update_open_positions_pnl(self):
        """Update floating PnL of open positions based on live prices."""
        try:
            from zohra.brokers.manager import broker_manager
        except ImportError:
            return

        for ticket, pos in list(self.open_positions.items()):
            try:
                tick = broker_manager.get_tick(pos["symbol"])
                if tick:
                    cur_price = tick["bid"] if pos["direction"] == "LONG" else tick["ask"]
                    pos["current_price"] = cur_price
                    
                    dir_mult = 1 if pos["direction"] == "LONG" else -1
                    contract_size = 100000.0 if "XAU" not in pos["symbol"] else 100.0
                    pips_gain = (cur_price - pos["entry_price"]) * dir_mult
                    gross_pnl = pips_gain * contract_size * pos["lots"]
                    
                    pos["profit"] = round(gross_pnl - pos["commission"], 2)

                    # Check stops
                    sl = pos["stop_loss"]
                    tp = pos["take_profit"]
                    if sl > 0 and ((pos["direction"] == "LONG" and cur_price < sl) or (pos["direction"] == "SHORT" and cur_price > sl)):
                        self.close_position(ticket, sl)
                    elif tp > 0 and ((pos["direction"] == "LONG" and cur_price > tp) or (pos["direction"] == "SHORT" and cur_price < tp)):
                        self.close_position(ticket, tp)
            except Exception:
                pass

    # ─── Event Publisher ──────────────────────────────────────

    @staticmethod
    def _emit_update_event(event_type: str, data: Any):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(event_bus.publish(event_type, data))
        except RuntimeError:
            pass  # No loop active


# Singleton
paper_engine = PaperTradingEngine()
