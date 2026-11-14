import logging
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger("zohra.sim_broker")

BASE_PRICES = {
    "EURUSD": 1.0850, "GBPUSD": 1.2750, "USDJPY": 155.50,
    "AUDUSD": 0.6650, "USDCAD": 1.3650, "USDCHF": 0.8950,
    "NZDUSD": 0.6150, "EURJPY": 168.50, "GBPJPY": 197.50,
    "AUDJPY": 103.50, "NZDJPY": 95.50, "EURGBP": 0.8550,
    "EURAUD": 1.6350, "GBPAUD": 1.9150, "EURCAD": 1.4850,
    "GBPCAD": 1.7450, "CADJPY": 113.50, "XAUUSD": 2330.00
}

class SimBroker:
    """
    Simulated Broker Layer:
    - Matches the exact MT5Broker interface.
    - Intercepts all trade execution and account balance queries, routing them to local memory.
    - Can wrap another broker (e.g. mt5_broker) for market data queries.
    """
    def __init__(self, initial_balance: float = 100000.0, base_broker = None):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        self.base_broker = base_broker
        self._connected = True
        
        self.open_positions_db: Dict[int, Dict] = {}
        self.next_ticket = 100000
        self.closed_trades_history: List[Dict] = []
        
        # Tick simulation caching
        self.last_ticks: Dict[str, Dict] = {}

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_account_info(self) -> Optional[Dict]:
        # Recalculate equity based on open position PnL
        open_pnl = sum(p.get("profit", 0.0) for p in self.open_positions_db.values())
        self.equity = self.balance + open_pnl
        return {
            "login": 999999,
            "server": "Zohra-Simulated",
            "equity": self.equity,
            "balance": self.balance,
            "margin": 0.0,
            "free_margin": self.equity,
            "profit": open_pnl,
            "leverage": 500,
            "currency": "USD",
        }

    def get_equity(self) -> float:
        info = self.get_account_info()
        return info["equity"] if info else self.balance

    def get_balance(self) -> float:
        return self.balance

    # --- Market Data ---
    def get_ohlcv(self, symbol: str, timeframe_str: str, count: int = 300) -> Optional[pd.DataFrame]:
        if self.base_broker and self.base_broker.is_connected():
            df = self.base_broker.get_ohlcv(symbol, timeframe_str, count)
            if df is not None:
                return df
        return self._generate_mock_ohlcv(symbol, timeframe_str, count)

    def get_multi_tf(self, symbol: str, timeframes: List[str], count: int = 300) -> Dict[str, Optional[pd.DataFrame]]:
        if self.base_broker and self.base_broker.is_connected():
            res = self.base_broker.get_multi_tf(symbol, timeframes, count)
            if res:
                # Ensure all requested timeframes have valid data, fallback to mock if None
                for tf in timeframes:
                    if res.get(tf) is None:
                        res[tf] = self.get_ohlcv(symbol, tf, count)
                return res
        return {tf: self.get_ohlcv(symbol, tf, count) for tf in timeframes}

    def _generate_mock_ohlcv(self, symbol: str, timeframe_str: str, count: int) -> pd.DataFrame:
        import numpy as np
        # Stable seed based on symbol/timeframe so it behaves reasonably
        np.random.seed(hash(symbol + timeframe_str) % 2**32)
        
        freq_map = {
            "M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
            "H1": "1h", "H4": "4h", "D1": "D"
        }
        freq = freq_map.get(timeframe_str.upper(), "1h")
        
        times = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=count, freq=freq)
        
        base_price = BASE_PRICES.get(symbol.upper(), 1.0000)
        
        # Generate wave + trend to trigger strategy entries
        is_up = (hash(symbol) % 2 == 0)
        x = np.linspace(0, 10 * np.pi, count)
        trend = np.linspace(0, base_price * 0.06, count)
        wave = np.sin(x) * base_price * 0.004
        
        if is_up:
            close_prices = base_price + trend + wave
        else:
            close_prices = base_price - trend + wave
            
        open_prices = np.roll(close_prices, 1)
        open_prices[0] = base_price
        
        high_prices = np.maximum(open_prices, close_prices) + (base_price * 0.001)
        low_prices = np.minimum(open_prices, close_prices) - (base_price * 0.001)
        
        df = pd.DataFrame({
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "tick_volume": np.random.randint(500, 1500, size=count),
        }, index=times)
        
        df.index.name = "time"
        return df

    def set_tick(self, symbol: str, bid: float, ask: float):
        """Helper for backtester to update current tick prices."""
        self.last_ticks[symbol] = {
            "bid": bid,
            "ask": ask,
            "time": int(datetime.utcnow().timestamp()),
            "spread": ask - bid
        }

    def get_tick(self, symbol: str) -> Optional[Dict]:
        if symbol in self.last_ticks:
            return self.last_ticks[symbol]
        if self.base_broker and self.base_broker.is_connected():
            tick = self.base_broker.get_tick(symbol)
            if tick is not None:
                return tick
        
        # Standalone mock generator for offline ticks
        price = BASE_PRICES.get(symbol.upper(), 1.0000)
        spread = 0.15 if "XAU" in symbol.upper() else (0.015 if "JPY" in symbol.upper() else 0.00015)
        return {"bid": price, "ask": price + spread, "time": int(datetime.utcnow().timestamp()), "spread": spread}

    def get_spread_pips(self, symbol: str) -> float:
        tick = self.get_tick(symbol)
        if not tick:
            return 1.5
        spread = tick["ask"] - tick["bid"]
        if "JPY" in symbol:
            return spread * 100
        elif "XAU" in symbol:
            return spread * 10
        else:
            return spread * 10000

    # --- Order Execution ---
    def open_trade(self, symbol: str, direction: str, lots: float,
                   stop_loss: float, take_profit: float,
                   magic: int = None, comment: str = "Zohra") -> Optional[Dict]:
        tick = self.get_tick(symbol)
        price = tick["ask"] if direction == "LONG" else tick["bid"]
        
        ticket = self.next_ticket
        self.next_ticket += 1
        
        pos = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "entry_price": price,
            "current_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "profit": 0.0,
            "magic": magic or 9999,
            "comment": comment,
            "open_time": datetime.utcnow().isoformat(),
        }
        self.open_positions_db[ticket] = pos
        logger.info(f"🔑 [SimBroker] Position opened: {symbol} {direction} {lots}L @ {price} | Ticket={ticket}")
        return pos

    def close_trade(self, ticket: int, symbol: str, direction: str,
                    lots: float = None, comment: str = "Zohra-Close") -> Optional[Dict]:
        if ticket not in self.open_positions_db:
            return None
            
        pos = self.open_positions_db[ticket]
        tick = self.get_tick(symbol)
        price = tick["bid"] if pos["direction"] == "LONG" else tick["ask"]
        
        pnl = self._calculate_pnl(pos, price)
        self.balance += pnl
        
        del self.open_positions_db[ticket]
        
        closed_record = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "lots": pos["lots"],
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "pnl": pnl,
            "open_time": pos["open_time"],
            "close_time": datetime.utcnow().isoformat(),
            "comment": comment
        }
        self.closed_trades_history.append(closed_record)
        logger.info(f"🔒 [SimBroker] Position closed: {symbol} Ticket={ticket} | PnL=${pnl:.2f}")
        return {"success": True, "pnl": pnl, "price": price, "ticket": ticket}

    def modify_trade(self, ticket: int, new_sl: float = None, new_tp: float = None) -> bool:
        if ticket not in self.open_positions_db:
            return False
        pos = self.open_positions_db[ticket]
        if new_sl is not None:
            pos["stop_loss"] = new_sl
        if new_tp is not None:
            pos["take_profit"] = new_tp
        return True

    def get_open_positions(self, magic: int = None, symbol: str = None) -> List[Dict]:
        for ticket, pos in list(self.open_positions_db.items()):
            tick = self.get_tick(pos["symbol"])
            cur_price = tick["bid"] if pos["direction"] == "LONG" else tick["ask"]
            pos["current_price"] = cur_price
            pos["profit"] = self._calculate_pnl(pos, cur_price)

        res = list(self.open_positions_db.values())
        if magic:
            res = [p for p in res if p["magic"] == magic]
        if symbol:
            res = [p for p in res if p["symbol"] == symbol]
        return res

    def close_all_positions(self, magic: int = None, comment: str = "Emergency-Close") -> int:
        positions = self.get_open_positions(magic=magic)
        closed = 0
        for pos in positions:
            res = self.close_trade(pos["ticket"], pos["symbol"], pos["direction"], comment=comment)
            if res and res.get("success"):
                closed += 1
        return closed

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        if self.base_broker and self.base_broker.is_connected():
            return self.base_broker.get_symbol_info(symbol)
        return {
            "symbol": symbol,
            "digits": 5 if "JPY" not in symbol else 3,
            "point": 0.00001 if "JPY" not in symbol else 0.001,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "contract": 100000.0,
        }

    def _calculate_pnl(self, pos: Dict, cur_price: float) -> float:
        contract_size = 100000.0
        if pos["symbol"] == "XAUUSD":
            contract_size = 100.0
        
        lots = pos["lots"]
        diff = (cur_price - pos["entry_price"]) if pos["direction"] == "LONG" else (pos["entry_price"] - cur_price)
        
        pnl = diff * contract_size * lots
        return round(pnl, 2)

    def check_sl_tp_fills(self):
        """Processes SL/TP breaches on open positions."""
        for ticket, pos in list(self.open_positions_db.items()):
            tick = self.get_tick(pos["symbol"])
            bid = tick["bid"]
            ask = tick["ask"]
            
            if pos["direction"] == "LONG":
                if pos["stop_loss"] > 0 and bid <= pos["stop_loss"]:
                    logger.info(f"💥 [SimBroker] Ticket={ticket} hit Stop Loss: {pos['stop_loss']}")
                    self.close_trade(ticket, pos["symbol"], "LONG", comment="SL_HIT")
                elif pos["take_profit"] > 0 and bid >= pos["take_profit"]:
                    logger.info(f"🎯 [SimBroker] Ticket={ticket} hit Take Profit: {pos['take_profit']}")
                    self.close_trade(ticket, pos["symbol"], "LONG", comment="TP_HIT")
            else:
                if pos["stop_loss"] > 0 and ask >= pos["stop_loss"]:
                    logger.info(f"💥 [SimBroker] Ticket={ticket} hit Stop Loss: {pos['stop_loss']}")
                    self.close_trade(ticket, pos["symbol"], "SHORT", comment="SL_HIT")
                elif pos["take_profit"] > 0 and ask <= pos["take_profit"]:
                    logger.info(f"🎯 [SimBroker] Ticket={ticket} hit Take Profit: {pos['take_profit']}")
                    self.close_trade(ticket, pos["symbol"], "SHORT", comment="TP_HIT")
