import logging
import datetime as dt
from typing import Dict, List, Optional
from zohra.config.settings import SYMBOL_REGISTRY, settings
from zohra.brokers.manager import broker_manager as mt5_broker
from zohra.core.symbol_resolver import symbol_resolver

logger = logging.getLogger("zohra.symbol_manager")

class SymbolManager:
    """
    Coordinates multi-asset registers, monitors health status,
    validates trading sessions, and processes live symbol switches.
    Restricted strictly to Gold (XAUUSD).
    """
    def __init__(self):
        self.symbols: Dict[str, Dict] = {s["symbol"]: s for s in SYMBOL_REGISTRY if s.get("enabled", True) and symbol_resolver.is_symbol_allowed(s.get("symbol"))}
        self.active_set = {s["symbol"] for s in SYMBOL_REGISTRY if s.get("enabled", True) and symbol_resolver.is_symbol_allowed(s.get("symbol"))}
        self.health_status: Dict[str, bool] = {}

    def get_symbol_params(self, symbol: str) -> Optional[Dict]:
        return self.symbols.get(symbol)

    def is_active(self, symbol: str) -> bool:
        # Check Hard Symbol Guard first
        if not symbol_resolver.is_symbol_allowed(symbol):
            return False
        # A configured symbol is eligible until broker verification explicitly
        # marks it unhealthy. The worker still performs that verification before
        # it can create a trade proposal.
        return symbol in self.active_set and self.health_status.get(symbol, True)

    def activate_symbol(self, symbol: str) -> bool:
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading disabled for {symbol}. Gold only mode is active.")
            return False
        if symbol in self.symbols:
            self.active_set.add(symbol)
            self.symbols[symbol]["enabled"] = True
            logger.info(f"🟢 Symbol {symbol} activated dynamically.")
            return True
        return False

    def deactivate_symbol(self, symbol: str) -> bool:
        if symbol in self.active_set:
            self.active_set.remove(symbol)
            if symbol in self.symbols:
                self.symbols[symbol]["enabled"] = False
            logger.warning(f"🔴 Symbol {symbol} deactivated dynamically.")
            return True
        return False

    def verify_broker_availability(self) -> Dict[str, bool]:
        """Verify Gold and Silver are supported, selected, and ticks available on MT5."""
        # Run broker resolution first
        resolved = symbol_resolver.resolve_broker_symbols()
        
        for symbol in list(self.symbols.keys()):
            if not symbol_resolver.is_symbol_allowed(symbol):
                self.health_status[symbol] = False
                continue

            try:
                from zohra.utils.mt5_connection import mt5
                if mt5:
                    mt5.symbol_select(symbol, True)
                
                info = mt5_broker.get_symbol_info(symbol)
                tick = mt5_broker.get_current_tick(symbol) if hasattr(mt5_broker, 'get_current_tick') else None
                if info is not None:
                    self.health_status[symbol] = True
                    logger.info(f"✅ Symbol '{symbol}' verified on MT5 (Digits={info.get('digits')}, Spread={info.get('spread')} pts)")
                else:
                    logger.warning(f"⚠️ Symbol '{symbol}' not visible or supported by MT5 broker.")
                    self.health_status[symbol] = False
            except Exception as e:
                logger.error(f"Error checking broker availability for {symbol}: {e}")
                self.health_status[symbol] = False
        return self.health_status

    def is_market_open(self, symbol: str) -> bool:
        """Determines if the trading session is open for the specified symbol."""
        params = self.get_symbol_params(symbol)
        
        # Crypto trades 24/7/365
        if params and (params.get("sector") == "Crypto" or params.get("broker") == "coindcx"):
            return True

        now_utc = dt.datetime.now(dt.timezone.utc)
        
        # Enforce general weekend shutdown (Friday 21:00 UTC to Sunday 21:00 UTC)
        weekday = now_utc.weekday()
        hour = now_utc.hour
        
        if weekday == 4 and hour >= 21: # Friday evening
            return False
        if weekday == 5: # Saturday
            return False
        if weekday == 6 and hour < 21: # Sunday before open
            return False

        # Sector specific filters (e.g. indices might have specific maintenance hours)
        if params and params.get("sector") == "Indices":
            # US100 / SPX500 close briefly daily (e.g. 21:00 to 22:00 UTC)
            if hour == 21:
                return False
                
        return True

symbol_manager = SymbolManager()
