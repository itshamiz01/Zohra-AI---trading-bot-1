import os
import json
import re

folders = [
    r"C:\Users\dell\Desktop\trading_bot",
    r"C:\Users\dell\Desktop\Trading Bot 2.0",
    r"C:\Users\dell\Desktop\Trading Bot 3.0"
]

symbols_json_data = {
  "symbols": [
    {
      "symbol": "XAUUSD",
      "sector": "Metals",
      "spread_limit": 4.5,
      "max_spread_pips": 4.5,
      "enabled": True,
      "contract_size": 100.0,
      "base_currency": "XAU",
      "quote_currency": "USD"
    },
    {
      "symbol": "GBPUSD",
      "sector": "Forex",
      "spread_limit": 2.5,
      "max_spread_pips": 2.5,
      "enabled": True,
      "contract_size": 100000.0,
      "base_currency": "GBP",
      "quote_currency": "USD"
    },
    {
      "symbol": "USDJPY",
      "sector": "Forex",
      "spread_limit": 2.5,
      "max_spread_pips": 2.5,
      "enabled": True,
      "contract_size": 100000.0,
      "base_currency": "USD",
      "quote_currency": "JPY"
    },
    {
      "symbol": "GBPJPY",
      "sector": "Forex",
      "spread_limit": 3.5,
      "max_spread_pips": 3.5,
      "enabled": True,
      "contract_size": 100000.0,
      "base_currency": "GBP",
      "quote_currency": "JPY"
    },
    {
      "symbol": "EURUSD",
      "sector": "Forex",
      "spread_limit": 2.0,
      "max_spread_pips": 2.0,
      "enabled": True,
      "contract_size": 100000.0,
      "base_currency": "EUR",
      "quote_currency": "USD"
    }
  ]
}

symbol_resolver_code = '''"""
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
'''

for folder in folders:
    print(f"Applying updates to {folder}...")
    
    # 1. Update symbols.json
    sym_json_path = os.path.join(folder, "zohra", "config", "symbols.json")
    with open(sym_json_path, "w", encoding="utf-8") as f:
        json.dump(symbols_json_data, f, indent=2)
    print(f"  Updated {sym_json_path}")
    
    # 2. Update symbol_resolver.py
    resolver_path = os.path.join(folder, "zohra", "core", "symbol_resolver.py")
    with open(resolver_path, "w", encoding="utf-8") as f:
        f.write(symbol_resolver_code)
    print(f"  Updated {resolver_path}")
    
    # 3. Update .env TRADED_SYMBOLS
    env_path = os.path.join(folder, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        new_lines = []
        found_traded = False
        for line in lines:
            if line.strip().startswith("TRADED_SYMBOLS"):
                new_lines.append("TRADED_SYMBOLS=XAUUSD,GBPUSD,USDJPY,GBPJPY,EURUSD\\n")
                found_traded = True
            else:
                new_lines.append(line)
        if not found_traded:
            new_lines.append("\\nTRADED_SYMBOLS=XAUUSD,GBPUSD,USDJPY,GBPJPY,EURUSD\\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print(f"  Updated {env_path}")
        
    # 4. Update settings.py
    settings_path = os.path.join(folder, "zohra", "config", "settings.py")
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        # Replace the hardcoded gold lines
        old_block = """# Strict Gold-Only Active Trading Universe
GOLD_SYMBOL: str = "XAUUSD"
ALLOWED_SYMBOLS: List[str] = ["XAUUSD"]
ALLOWED_METALS: List[str] = ["XAUUSD"]
for symbol in SYMBOL_REGISTRY:
    symbol["enabled"] = (symbol["symbol"] == "XAUUSD")

# Derived symbols configuration — STRICTLY GOLD (XAUUSD) ONLY
FOREX_PAIRS: List[str] = []
GOLD_PAIRS: List[str] = ["XAUUSD"]
INDICES: List[str] = []
ACTIVE_PAIRS: List[str] = ["XAUUSD"]

# Override active symbols from .env if set, filtered strictly to Gold
_env_traded = os.getenv("TRADED_SYMBOLS", "")
if _env_traded:
    ACTIVE_PAIRS = [s.strip() for s in _env_traded.split(",") if s.strip() and s.strip() in ALLOWED_SYMBOLS]
if not ACTIVE_PAIRS:
    ACTIVE_PAIRS = ["XAUUSD"]"""

        new_block = """# Multi-Asset Universe Configuration
GOLD_SYMBOL: str = "XAUUSD"
ALLOWED_SYMBOLS: List[str] = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]
ALLOWED_METALS: List[str] = ["XAUUSD"]
FOREX_PAIRS: List[str] = ["GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]
GOLD_PAIRS: List[str] = ["XAUUSD"]
INDICES: List[str] = []
ACTIVE_PAIRS: List[str] = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]

for symbol in SYMBOL_REGISTRY:
    symbol["enabled"] = symbol.get("symbol") in ALLOWED_SYMBOLS

# Override active symbols from .env if set
_env_traded = os.getenv("TRADED_SYMBOLS", "")
if _env_traded:
    parsed_symbols = [s.strip().upper() for s in _env_traded.split(",") if s.strip()]
    if parsed_symbols:
        ACTIVE_PAIRS = parsed_symbols
        ALLOWED_SYMBOLS = list(dict.fromkeys(ALLOWED_SYMBOLS + parsed_symbols))
if not ACTIVE_PAIRS:
    ACTIVE_PAIRS = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]"""

        if old_block in content:
            content = content.replace(old_block, new_block)
        else:
            # Regex or direct substitution
            content = re.sub(
                r'ALLOWED_SYMBOLS:\s*List\[str\]\s*=\s*\["XAUUSD"\]',
                'ALLOWED_SYMBOLS: List[str] = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]',
                content
            )
            content = re.sub(
                r'ACTIVE_PAIRS:\s*List\[str\]\s*=\s*\["XAUUSD"\]',
                'ACTIVE_PAIRS: List[str] = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]',
                content
            )
            content = re.sub(
                r'FOREX_PAIRS:\s*List\[str\]\s*=\s*\[\]',
                'FOREX_PAIRS: List[str] = ["GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]',
                content
            )
            
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Updated {settings_path}")
        
    # 5. Update bot_profile.py
    bot_profile_path = os.path.join(folder, "zohra", "config", "bot_profile.py")
    if os.path.exists(bot_profile_path):
        with open(bot_profile_path, "r", encoding="utf-8", errors="ignore") as f:
            b_content = f.read()
        b_content = b_content.replace(
            'allowed_symbols=["XAUUSD"]',
            'allowed_symbols=["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"]'
        )
        b_content = b_content.replace(
            'allowed_symbols: List[str] = field(default_factory=lambda: ["XAUUSD"])',
            'allowed_symbols: List[str] = field(default_factory=lambda: ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURUSD"])'
        )
        with open(bot_profile_path, "w", encoding="utf-8") as f:
            f.write(b_content)
        print(f"  Updated {bot_profile_path}")

print("All updates applied successfully!")
