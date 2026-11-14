"""
Trade Execution via MetaTrader 5
All orders routed through MT5 terminal.
"""

from datetime import datetime
from typing import Optional, Dict

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MAGIC_NUMBER, LOT_STEP, MIN_LOT_SIZE, MAX_LOT_SIZE
from database import db


class TradeExecutor:
    """
    Executes orders via MetaTrader 5.
    Supports both demo and live accounts.
    """

    def __init__(self):
        self._connected = False

    def connect(self) -> bool:
        """Initialize MT5 connection."""
        if not MT5_AVAILABLE:
            db.log_system("ERROR", "MetaTrader5 package not installed.")
            return False
        if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            db.log_system("ERROR", f"MT5 init failed: {mt5.last_error()}")
            return False
        self._connected = True
        info = mt5.account_info()
        db.log_system("INFO", f"MT5 connected: #{info.login} | {info.server} | ${info.equity:.2f}")
        return True

    def _get_filling(self, symbol: str) -> int:
        """Return the correct filling mode for the symbol."""
        if not MT5_AVAILABLE:
            return 0
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_FOK
        fm = info.filling_mode
        if fm & 1: return mt5.ORDER_FILLING_FOK
        if fm & 2: return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def open_position(self, trade: Dict) -> Dict:
        """
        Open a market order via MT5.
        Returns result dict with mt5_ticket.
        """
        if not MT5_AVAILABLE:
            db.log_system("WARNING", "MT5 not available — trade simulated")
            return {"success": False, "error": "MT5 not available"}

        symbol    = trade["symbol"]
        direction = trade["direction"]
        lots      = float(trade.get("lots", trade.get("position_size", 0.01)))

        # Snap to broker lot step
        lots = round(round(lots / LOT_STEP) * LOT_STEP, 2)
        lots = max(MIN_LOT_SIZE, min(lots, MAX_LOT_SIZE))

        if not mt5.symbol_select(symbol, True):
            return {"success": False, "error": f"Symbol {symbol} not found"}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "error": "No tick data"}

        if direction == "LONG":
            order_type = mt5.ORDER_TYPE_BUY
            price      = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price      = tick.bid

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       lots,
            "type":         order_type,
            "price":        price,
            "sl":           round(trade.get("stop_price", trade.get("stop_loss", 0)), 5),
            "tp":           round(trade.get("target_price", trade.get("take_profit", 0)), 5),
            "deviation":    10,
            "magic":        MAGIC_NUMBER,
            "comment":      "Zohra",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling(symbol),
        }

        result = mt5.order_send(request)

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            mt5_ticket = result.order

            db.log_system("INFO",
                f"MT5 trade opened: {symbol} {direction} {lots}L @ {price:.5f} | Ticket={mt5_ticket}")

            trade["entry_price"]    = price
            trade["timestamp_open"] = datetime.utcnow().isoformat()
            trade["mt5_ticket"]     = mt5_ticket

            db.log_trade(trade)

            return {
                "success":    True,
                "mt5_ticket": mt5_ticket,
                "fill_price": price,
            }
        else:
            err = f"MT5 order failed: {result.retcode} — {result.comment}"
            db.log_system("ERROR", err)
            return {"success": False, "error": err}

    def close_position(self, trade_id: str, mt5_ticket: int,
                       symbol: str, direction: str) -> Dict:
        """
        Close a specific MT5 position by ticket.
        """
        if not MT5_AVAILABLE:
            return {"success": False, "error": "MT5 not available"}

        positions = mt5.positions_get(ticket=mt5_ticket)
        if not positions:
            db.log_system("WARNING", f"No open position found for ticket {mt5_ticket}")
            return {"success": False, "error": "Position not found"}

        pos  = positions[0]
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "error": "No tick data"}

        # Close = opposite side
        if pos.type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            close_price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            close_price = tick.ask

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       pos.volume,
            "type":         close_type,
            "position":     mt5_ticket,
            "price":        close_price,
            "deviation":    10,
            "magic":        MAGIC_NUMBER,
            "comment":      "Zohra-Close",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling(symbol),
        }

        result     = mt5.order_send(request)
        realized_pnl = pos.profit

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            # Compute pnl_pct from DB
            cursor = db.conn.cursor()
            cursor.execute(
                "SELECT entry_price, risk_usd FROM trades WHERE trade_id = ?", (trade_id,)
            )
            row = cursor.fetchone()
            pnl_pct = (realized_pnl / row[1] * 100) if row and row[1] else 0

            db.close_trade(trade_id, close_price, realized_pnl, pnl_pct,
                           "MANUAL_CLOSE", str(mt5_ticket))

            db.log_system("INFO",
                f"Closed {symbol}: P&L ${realized_pnl:.2f} ({pnl_pct:.1f}% of risk) | Ticket={mt5_ticket}")

            return {
                "success":    True,
                "exit_price": close_price,
                "pnl_usd":    realized_pnl,
                "pnl_pct":    pnl_pct,
            }
        else:
            err = f"MT5 close failed: {result.retcode} — {result.comment}"
            db.log_system("ERROR", err)
            return {"success": False, "error": err}

    def modify_stop(self, mt5_ticket: int, new_stop: float) -> bool:
        """Update stop loss on an open MT5 position."""
        if not MT5_AVAILABLE:
            return False

        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "position": mt5_ticket,
            "sl":       round(new_stop, 5),
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return True
        db.log_system("ERROR", f"MT5 modify_stop failed: {result.retcode}")
        return False

    def get_trade_details(self, mt5_ticket: int) -> Dict:
        """Get current status of a MT5 position."""
        if not MT5_AVAILABLE:
            return {}
        positions = mt5.positions_get(ticket=mt5_ticket)
        if not positions:
            return {}
        pos = positions[0]
        return {
            "ticket":        pos.ticket,
            "symbol":        pos.symbol,
            "direction":     "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT",
            "lots":          pos.volume,
            "entry_price":   pos.price_open,
            "current_price": pos.price_current,
            "stop_loss":     pos.sl,
            "take_profit":   pos.tp,
            "profit":        pos.profit,
        }


# Singleton
executor = TradeExecutor()
