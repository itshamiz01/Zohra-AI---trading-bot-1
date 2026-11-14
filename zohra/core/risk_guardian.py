"""
╔══════════════════════════════════════════════════════════════════════╗
║                    ZOHRA — RISK GUARDIAN SYSTEM                      ║
║            Supreme Risk Authority & Veto Logic Core                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, Any, List, Tuple
from zohra.config.settings import (
    STATE, MAX_OPEN_POSITIONS, MAX_SCALE_UP_TICKETS_PER_SYMBOL,
    MAX_DRAWDOWN_PCT, MAX_SECTOR_POSITIONS, METAL_SYMBOLS
)
from zohra.brokers.manager import broker_manager as mt5_broker

logger = logging.getLogger("zohra.guardian")

class RiskGuardian:
    """
    Supreme risk authority.
    Overrides all strategies, LLMs, and agent committees.
    Implements daily, weekly, monthly drawdown limits and portfolio correlation/exposure filters.
    """
    def __init__(self, max_drawdown_pct: float = 8.0, max_spread_pips: float = 3.5):
        self.max_drawdown_pct = max_drawdown_pct
        self.max_spread_pips = max_spread_pips
        
        # Drawdown limit settings
        self.daily_limit_pct = 2.0
        self.weekly_limit_pct = 5.0
        self.monthly_limit_pct = 8.0

    def evaluate_execution_safety(self, symbol: str, direction: str, size_lots: float, 
                                  open_positions: List[Dict] = None, is_probe: bool = False) -> Tuple[bool, str]:
        """
        Runs critical safety filters. Returns (is_safe, reason).
        """
        # 0. Central Hard Symbol Guard — Strictly Gold (XAUUSD) Only
        from zohra.core.symbol_resolver import symbol_resolver
        from zohra.core.symbol_manager import symbol_manager
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading disabled for {symbol}. Gold only mode is active.")
            return False, f"BLOCKED: Trading disabled for {symbol}. Gold only mode is active."

        sym_params = symbol_manager.get_symbol_params(symbol) or {}

        def sector_for(instrument: str) -> str:
            params = symbol_manager.get_symbol_params(instrument) or {}
            if params.get("sector"):
                return params["sector"]
            normalized = str(instrument or "").upper()
            if normalized in METAL_SYMBOLS or normalized.startswith(("XAU", "XAG", "GOLD", "SILVER")):
                return "Metals"
            if len(normalized) >= 6 and normalized[:6].isalpha():
                return "Forex"
            return "Unknown"

        # 1. Global Halt checks
        if STATE.trading_halted:
            return False, f"Trading is halted: {STATE.halt_reason}"

        # 2. Connection checks
        if not mt5_broker.is_connected():
            return False, "Broker terminal is offline / disconnected."

        # 3. Drawdown checks
        equity = mt5_broker.get_equity()
        if equity <= 0:
            return False, "Invalid equity check: broker returned <= 0."

        if STATE.peak_equity > 0:
            drawdown_pct = max(0.0, (STATE.peak_equity - equity) / STATE.peak_equity * 100.0)
            if drawdown_pct > self.max_drawdown_pct:
                return False, f"Safety halt: Drawdown is {drawdown_pct:.2f}% (Limit: {self.max_drawdown_pct}%)"

        # Period starting equities
        daily_start = getattr(STATE, "daily_start_equity", 0.0)
        weekly_start = getattr(STATE, "weekly_start_equity", 0.0)
        monthly_start = getattr(STATE, "monthly_start_equity", 0.0)

        if daily_start > 0:
            daily_loss_pct = (daily_start - equity) / daily_start * 100.0
            if daily_loss_pct > self.daily_limit_pct:
                return False, f"Daily limit exceeded: Loss is {daily_loss_pct:.2f}% (Limit: {self.daily_limit_pct}%)"

        if weekly_start > 0:
            weekly_loss_pct = (weekly_start - equity) / weekly_start * 100.0
            if weekly_loss_pct > self.weekly_limit_pct:
                return False, f"Weekly limit exceeded: Loss is {weekly_loss_pct:.2f}% (Limit: {self.weekly_limit_pct}%)"

        if monthly_start > 0:
            monthly_loss_pct = (monthly_start - equity) / monthly_start * 100.0
            if monthly_loss_pct > self.monthly_limit_pct:
                return False, f"Monthly limit exceeded: Loss is {monthly_loss_pct:.2f}% (Limit: {self.monthly_limit_pct}%)"

        # 4. Exposure / Position Count check
        if open_positions is None:
            open_positions = mt5_broker.get_open_positions() or []
            
        # Prevent multiple concurrent probe positions on the same symbol
        if is_probe and any(p["symbol"] == symbol for p in open_positions):
            return False, f"Probe veto: active position already exists for {symbol}."

        # ── Per-symbol scale-up ticket limit ──
        symbol_position_count = sum(1 for p in open_positions if p.get("symbol") == symbol)
        if symbol_position_count >= MAX_SCALE_UP_TICKETS_PER_SYMBOL:
            return False, f"Scale-up limit reached for {symbol}. Max {MAX_SCALE_UP_TICKETS_PER_SYMBOL} tickets per symbol."

        # ── Global position limit — enforced even for scale-ups ──
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            return False, f"Maximum open position limit ({MAX_OPEN_POSITIONS}) reached."

        # ── Sector exposure check ──
        sector = sector_for(symbol)
        max_sector = MAX_SECTOR_POSITIONS.get(sector, 3)
        sector_count = sum(
            1 for position in open_positions if sector_for(position.get("symbol", "")) == sector
        )
        if sector_count >= max_sector:
            return False, f"Sector exposure limit for {sector} ({max_sector}) reached."

        # 5. Spread stability check (Accurate Pip Calculations for Gold & Silver)
        symbol_info = mt5_broker.get_symbol_info(symbol)
        if symbol_info:
            spread = symbol_info.get("spread", 999)
            point = symbol_info.get("point", 0.01)
            digits = symbol_info.get("digits", 2)
            
            # Accurate Pip Conversions:
            # Gold (XAUUSD): 1 pip = 0.10 price change (e.g. 29 points at point 0.01 is 2.9 pips)
            # Silver (XAGUSD): 1 pip = 0.01 price change (e.g. 34 points at point 0.001 is 3.4 pips)
            if "XAU" in symbol or symbol == "GOLD":
                spread_pips = (spread * point) / 0.10 if point > 0 else spread * 0.1
            elif "XAG" in symbol or symbol == "SILVER":
                spread_pips = (spread * point) / 0.01 if point > 0 else spread * 0.1
            elif "JPY" in symbol:
                spread_pips = spread * point * 100.0
            else:
                spread_pips = spread * point * 10000.0

            max_allowed = (sym_params.get("max_spread_pips", 5.0) if symbol in METAL_SYMBOLS
                           else self.max_spread_pips)
            if spread_pips > max_allowed:
                return False, f"High spread detected on {symbol}: {spread_pips:.1f} pips > {max_allowed:.1f} max limit."

        # 6. Correlation & Currency Concentration Veto
        if open_positions:
            # Net Currency Exposure Limits (e.g. USD)
            currency_basket = {}
            for pos in open_positions:
                p_symbol = pos.get("symbol", "")
                p_lots = pos.get("lots", pos.get("position_size_lots", 0.0))
                p_dir = pos.get("direction", "LONG")
                if "type" in pos:
                    p_dir = "LONG" if pos["type"] == 0 else "SHORT"
                    
                base = p_symbol[:3]
                quote = p_symbol[3:6]
                if p_symbol == "XAUUSD":
                    base, quote = "XAU", "USD"
                elif p_symbol == "XAGUSD":
                    base, quote = "XAG", "USD"
                mult = 1.0 if p_dir == "LONG" else -1.0
                currency_basket[base] = currency_basket.get(base, 0.0) + p_lots * mult
                currency_basket[quote] = currency_basket.get(quote, 0.0) - p_lots * mult
            
            # Prevent USD concentration > 2.0 lots
            usd_exposure = currency_basket.get("USD", 0.0)
            if abs(usd_exposure) >= 2.0:
                # If adding this trade increases exposure, veto it
                base = symbol[:3]
                quote = symbol[3:6]
                if symbol == "XAUUSD":
                    base, quote = "XAU", "USD"
                elif symbol == "XAGUSD":
                    base, quote = "XAG", "USD"
                direction_mult = 1.0 if direction == "LONG" else -1.0
                potential_change = 0.0
                if base == "USD": potential_change += size_lots * direction_mult
                if quote == "USD": potential_change -= size_lots * direction_mult
                
                if abs(usd_exposure + potential_change) > abs(usd_exposure):
                    return False, f"Concentration Veto: USD net exposure ({usd_exposure:+.2f} lots) exceeds 2.0 lots limit."

            # Correlation Filter Veto
            try:
                from zohra.core.correlation_engine import correlation_engine
                for pos in open_positions:
                    p_symbol = pos.get("symbol", "")
                    if p_symbol == symbol:
                        continue

                    # Exempt metal-to-metal correlation (naturally correlated, we want both)
                    if symbol in METAL_SYMBOLS and p_symbol in METAL_SYMBOLS:
                        continue
                    
                    p_dir = pos.get("direction", "LONG")
                    if "type" in pos:
                        p_dir = "LONG" if pos["type"] == 0 else "SHORT"
                    
                    # Get correlation coefficient
                    corr = correlation_engine.get_correlation(symbol, p_symbol)
                    
                    # If highly correlated (> 0.7) and in the same direction, or highly inverse (< -0.7) in opposite direction
                    same_dir = (p_dir == direction)
                    if (corr >= 0.7 and same_dir) or (corr <= -0.7 and not same_dir):
                        return False, f"Correlation Veto: High correlation ({corr:.2f}) with active {p_symbol} ({p_dir}) position."
            except Exception as e:
                logger.error(f"RiskGuardian correlation filter error: {e}")

        return True, "Passed Risk Guardian validation."

# Singleton
risk_guardian = RiskGuardian()
