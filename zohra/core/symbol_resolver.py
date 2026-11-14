"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — CENTRAL SYMBOL RESOLVER                      ║
║         Multi-Asset Universe: XAUUSD, GBPUSD, USDJPY, GBPJPY, EURUSD ║
║              Hard Symbol Guard & Broker Variant Resolver             ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("zohra.symbol_resolver")

# Master canonical target instruments
CANONICAL_GOLD = "XAUUSD"
DEFAULT_ALLOWED_SYMBOLS = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]
ALLOWED_CANONICAL_SYMBOLS = DEFAULT_ALLOWED_SYMBOLS
ALLOWED_SYMBOLS = DEFAULT_ALLOWED_SYMBOLS


class SymbolResolver:
    """
    Centralized Symbol Resolver and Hard Symbol Guard.
    Resolves broker-specific symbol naming variations (e.g. XAUUSDm, GBPUSD.a, EURUSD.pro).
    Enforces that active trading is permitted on allowed universe symbols.
    """

    def __init__(self):
        self._resolved_symbols: Dict[str, str] = {s: s for s in DEFAULT_ALLOWED_SYMBOLS}
        self._broker_to_canonical: Dict[str, str] = {s: s for s in DEFAULT_ALLOWED_SYMBOLS}
        self._canonical_to_broker: Dict[str, str] = {s: s for s in DEFAULT_ALLOWED_SYMBOLS}
        self._is_resolved = False

    @property
    def gold_symbol(self) -> str:
        """Returns the broker-resolved Gold symbol name."""
        return self._canonical_to_broker.get(CANONICAL_GOLD, CANONICAL_GOLD)

    @property
    def allowed_symbols(self) -> Dict[str, str]:
        """Returns map of canonical -> broker_sym."""
        return self._resolved_symbols

    @property
    def active_symbols_list(self) -> List[str]:
        """Returns list of active broker symbol names."""
        from zohra.config.settings import ACTIVE_PAIRS
        return [self._canonical_to_broker.get(s, s) for s in ACTIVE_PAIRS]

    def resolve_broker_symbols(self) -> Dict[str, str]:
        """
        Queries MT5 terminal to detect and bind exact broker symbol names for active universe.
        """
        try:
            from zohra.utils.mt5_connection import mt5, MT5_AVAILABLE
            if not MT5_AVAILABLE or not mt5.terminal_info():
                logger.info("ℹ️ MT5 not connected yet; using default canonical symbols.")
                return self._resolved_symbols

            from zohra.config.settings import ACTIVE_PAIRS
            symbols_to_resolve = list(dict.fromkeys(DEFAULT_ALLOWED_SYMBOLS + ACTIVE_PAIRS))

            for canon in symbols_to_resolve:
                if canon == "XAUUSD":
                    variants = ["XAUUSD", "XAUUSDm", "XAUUSD.a", "XAUUSD.raw", "XAUUSD.pro", "GOLD", "GOLDm"]
                else:
                    variants = [
                        canon,
                        f"{canon}m",
                        f"{canon}.a",
                        f"{canon}.raw",
                        f"{canon}.pro",
                        f"{canon}_i",
                        f"{canon}+",
                        f"{canon}."
                    ]

                resolved = None
                for v in variants:
                    info = mt5.symbol_info(v)
                    if info is not None:
                        mt5.symbol_select(v, True)
                        tick = mt5.symbol_info_tick(v)
                        if tick and tick.bid > 0:
                            resolved = v
                            break
                        elif resolved is None:
                            resolved = v

                if resolved:
                    self._resolved_symbols[canon] = resolved
                    self._canonical_to_broker[canon] = resolved
                    self._broker_to_canonical[resolved.upper()] = canon
                    logger.info(f"🪙 Resolved symbol: '{canon}' -> Broker '{resolved}'")
                else:
                    self._resolved_symbols[canon] = canon
                    self._canonical_to_broker[canon] = canon
                    self._broker_to_canonical[canon.upper()] = canon
                    logger.warning(f"⚠️ Symbol {canon} not explicitly matched; using '{canon}'")

            self._is_resolved = True
        except Exception as e:
            logger.error(f"Error during symbol resolution: {e}")

        return self._resolved_symbols

    def is_symbol_allowed(self, symbol: str) -> bool:
        """
        Hard Symbol Guard Check:
        Returns True if symbol is in the allowed universe (canonical or broker variant).
        """
        if not symbol:
            return False
        clean_sym = symbol.strip().upper()
        from zohra.config.settings import ACTIVE_PAIRS, ALLOWED_SYMBOLS as SETTINGS_ALLOWED

        allowed_canonicals = {s.upper() for s in (DEFAULT_ALLOWED_SYMBOLS + ACTIVE_PAIRS + SETTINGS_ALLOWED)}
        
        # Direct check
        if clean_sym in allowed_canonicals:
            return True
        
        # Check canonical mapping
        canon = self._broker_to_canonical.get(clean_sym)
        if canon and canon.upper() in allowed_canonicals:
            return True

        # Check prefix/suffix variants
        for allowed in allowed_canonicals:
            if clean_sym.startswith(allowed) or (allowed == "XAUUSD" and clean_sym.startswith("GOLD")):
                return True

        return False

    def enforce_guard(self, symbol: str, context: str = "Execution") -> Tuple[bool, str]:
        """
        Validates symbol against Hard Symbol Guard.
        If disallowed, returns (False, error_reason).
        """
        if not self.is_symbol_allowed(symbol):
            reason = f"BLOCKED: Trading disabled for {symbol}. Not in allowed universe."
            logger.warning(f"🚫 HARD_SYMBOL_GUARD_VETO [{context}]: {reason}")
            return False, reason
        return True, "SYMBOL_ALLOWED"

    def is_allowed(self, symbol: str) -> bool:
        """Alias for is_symbol_allowed."""
        return self.is_symbol_allowed(symbol)

    def guard(self, symbol: str, context: str = "Execution") -> bool:
        """Boolean guard returning True if allowed, False if prohibited (logs rejection)."""
        allowed, _ = self.enforce_guard(symbol, context=context)
        return allowed

    def enforce_symbol_guard(self, symbol: str, context: str = "Execution") -> Tuple[bool, str]:
        """Alias for enforce_guard."""
        return self.enforce_guard(symbol, context=context)

    def get_canonical_symbol(self, broker_symbol: str) -> str:
        """Translates broker symbol name back to canonical."""
        if not broker_symbol:
            return CANONICAL_GOLD
        clean = broker_symbol.strip().upper()
        return self._broker_to_canonical.get(clean, clean)


# Global singleton instance
symbol_resolver = SymbolResolver()
