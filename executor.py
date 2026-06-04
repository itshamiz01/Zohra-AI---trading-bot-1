"""
Trade Execution via MetaTrader 5 Python API
Paper trading uses a MT5 Demo account — identical API to live.
"""

from datetime import datetime
from typing import Optional, Dict

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MIN_LOT_SIZE, MAX_LOT_SIZE, LOT_STEP
from database import db

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


# ── Lot / Unit Conversion ──────────────────────────────────────────────────

def units_to_lots(units: int, symbol: str) -> float:
    """
    Convert OANDA-style units to MT5 lots.
    1 standard lot = 100,000 units for most FX pairs.
    Clamps to broker min/max and rounds to LOT_STEP precision.
    """
    lots = units / 100_000
    # Snap to valid lot step
    lots = round(round(lots / LOT_STEP) * LOT_STEP, 2)
    lots = max(MIN_LOT_SIZE, min(lots, MAX_LOT_SIZE))
    return lots


def _round_price(symbol: str, price: float) -> float:
    """Round price to the symbol's required digits."""
    if not MT5_AVAILABLE:
        return round(price, 5)
    info = mt5.symbol_info(symbol)
    if info is None:
        return round(price, 5)
    digits = info.digits
    return round(price, digits)


def _get_filling_mode(symbol: str) -> int:
    """Auto-detect the broker's supported order filling mode for a symbol.
    filling_mode is a bitmask: bit0(1)=FOK, bit1(2)=IOC, bit2(4)=RETURN
    """
    if not MT5_AVAILABLE:
        return 0
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1:    # FOK supported
        return mt5.ORDER_FILLING_FOK
    elif fm & 2:  # IOC supported
        return mt5.ORDER_FILLING_IOC
    elif fm & 4:  # RETURN supported
        return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_FOK


# ── Trade Executor ─────────────────────────────────────────────────────────

class TradeExecutor:
    """
    Executes orders via MetaTrader 5 Python API.
    All trades target the demo account (paper trading).
    """

    MAGIC = 20240101   # Unique identifier for this bot's orders in MT5

    def open_position(self, trade: Dict) -> Dict:
        """
        Open a new market order with built-in SL and TP.
        Returns {"success": bool, "mt5_ticket": int, "fill_price": float}
        """
        if not MT5_AVAILABLE:
            return {"success": False, "error": "MetaTrader5 package not installed"}

        symbol    = trade["symbol"]
        direction = trade["direction"]
        units     = trade["position_size"]   # OANDA units from risk_manager
        lots      = units_to_lots(units, symbol)

        sl = _round_price(symbol, trade["stop_price"])
        tp = _round_price(symbol, trade["target_price"])

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            error = f"Cannot get tick for {symbol}: {mt5.last_error()}"
            db.log_system("ERROR", error)
            return {"success": False, "error": error}

        if direction == "LONG":
            order_type = mt5.ORDER_TYPE_BUY
            price      = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price      = tick.bid

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      symbol,
            "volume":      lots,
            "type":        order_type,
            "price":       price,
            "sl":          sl,
            "tp":          tp,
            "deviation":   20,           # max slippage in points
            "magic":       self.MAGIC,
            "comment":     "EMA_ATR_Bot",
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": _get_filling_mode(symbol),
        }

        db.log_system("INFO",
            f"Sending {direction} order: {lots} lots {symbol} @ ~{price:.5f} "
            f"SL={sl:.5f} TP={tp:.5f}")

        result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else str(mt5.last_error())
            error = f"Order failed retcode={retcode}: {comment}"
            db.log_system("ERROR", error)
            return {"success": False, "error": error}

        ticket      = result.order
        fill_price  = result.price if result.price else price

        db.log_system("INFO",
            f"Position opened: {symbol} ticket={ticket} fill={fill_price:.5f} {lots} lots")

        # Store MT5 ticket as oanda_trade_id for DB compatibility
        trade["entry_price"]    = fill_price
        trade["timestamp_open"] = datetime.utcnow().isoformat()
        trade["oanda_trade_id"] = str(ticket)   # reuse column for MT5 ticket

        db.log_trade(trade)

        return {
            "success":   True,
            "mt5_ticket": ticket,
            "fill_price": fill_price,
        }

    def close_position(self, trade_id: str, oanda_trade_id: str,
                       symbol: str, direction: str) -> Dict:
        """
        Close a specific open position by MT5 ticket number.
        oanda_trade_id stores the MT5 ticket (for DB compatibility).
        """
        if not MT5_AVAILABLE:
            return {"success": False, "error": "MetaTrader5 package not installed"}

        ticket = int(oanda_trade_id)

        # Find the position
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            error = f"Position ticket={ticket} not found"
            db.log_system("ERROR", error)
            return {"success": False, "error": error}

        pos  = positions[0]
        lots = pos.volume
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "error": f"Cannot get tick for {symbol}"}

        # Close = opposite order type
        if pos.type == 0:   # was BUY → close with SELL
            close_type = mt5.ORDER_TYPE_SELL
            price      = tick.bid
        else:               # was SELL → close with BUY
            close_type = mt5.ORDER_TYPE_BUY
            price      = tick.ask

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      symbol,
            "volume":      lots,
            "type":        close_type,
            "position":    ticket,       # link to the open position
            "price":       price,
            "deviation":   20,
            "magic":       self.MAGIC,
            "comment":     "EMA_ATR_Bot_Close",
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": _get_filling_mode(symbol),
        }

        result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else str(mt5.last_error())
            error = f"Close failed retcode={retcode}: {comment}"
            db.log_system("ERROR", error)
            return {"success": False, "error": error}

        exit_price    = result.price if result.price else price
        realized_pnl  = pos.profit   # Last known unrealized becomes realized

        # Fetch actual realized P&L from deal history
        from datetime import timedelta
        deals = mt5.history_deals_get(
            datetime.utcnow() - timedelta(seconds=10),
            datetime.utcnow() + timedelta(seconds=5),
        )
        if deals:
            matching = [d for d in deals if d.position_id == ticket]
            if matching:
                realized_pnl = sum(d.profit for d in matching)

        # Calculate pnl_pct against risk_usd stored in DB
        db_cursor = db.conn.cursor()
        db_cursor.execute(
            "SELECT entry_price, risk_usd FROM trades WHERE trade_id = ?",
            (trade_id,)
        )
        row = db_cursor.fetchone()
        pnl_pct = 0.0
        if row:
            _, risk_usd = row
            if risk_usd and risk_usd > 0:
                pnl_pct = (realized_pnl / risk_usd) * 100

        db.close_trade(trade_id, exit_price, realized_pnl, pnl_pct,
                       "MANUAL_CLOSE", oanda_trade_id)

        db.log_system("INFO",
            f"Closed {symbol} ticket={ticket}: P&L ${realized_pnl:.2f} ({pnl_pct:.1f}%)")

        return {
            "success":    True,
            "exit_price": exit_price,
            "pnl_usd":    realized_pnl,
            "pnl_pct":    pnl_pct,
        }

    def modify_stop(self, oanda_trade_id: str, new_stop: float) -> bool:
        """
        Update the stop loss on an open MT5 position.
        Uses TRADE_ACTION_SLTP which modifies SL/TP without placing a new order.
        """
        if not MT5_AVAILABLE:
            return False

        ticket = int(oanda_trade_id)
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            db.log_system("ERROR", f"modify_stop: ticket={ticket} not found")
            return False

        pos    = positions[0]
        symbol = pos.symbol
        sl     = _round_price(symbol, new_stop)

        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "symbol":   symbol,
            "position": ticket,
            "sl":       sl,
            "tp":       pos.tp,   # preserve existing TP
        }

        result = mt5.order_send(request)
        success = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

        if not success:
            retcode = result.retcode if result else "None"
            db.log_system("ERROR",
                f"modify_stop failed for ticket={ticket} retcode={retcode}")

        return success

    def get_trade_details(self, oanda_trade_id: str) -> Dict:
        """Get current status of an open trade by ticket."""
        if not MT5_AVAILABLE:
            return {}

        ticket    = int(oanda_trade_id)
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {}

        pos = positions[0]
        return {
            "ticket":         pos.ticket,
            "symbol":         pos.symbol,
            "volume":         pos.volume,
            "price_open":     pos.price_open,
            "sl":             pos.sl,
            "tp":             pos.tp,
            "profit":         pos.profit,
            "type":           "BUY" if pos.type == 0 else "SELL",
        }


# Singleton instance
executor = TradeExecutor()
