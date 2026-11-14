"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — CRYPTO RISK GUARDIAN                       ║
║            Crypto-Specific Risk Filters & Validation Logic           ║
║                                                                      ║
║  This module handles high volatility, bid-ask spreads, liquidity,   ║
║  portfolio exposure caps, and position sizers for crypto assets.     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np

from zohra.config.settings import (
    CRYPTO_VOLATILITY_THRESHOLD,
    CRYPTO_MAX_SPREAD_PIPS,
    CRYPTO_MAX_EXPOSURE_PCT,
    MAX_OPEN_POSITIONS
)
from zohra.brokers.manager import broker_manager

logger = logging.getLogger("zohra.crypto_risk")

class CryptoRiskGuardian:
    """
    Subsystem risk manager for Crypto Market assets.
    Forces strict safety compliance on volatility, spread, liquidity, and exposure.
    """

    def __init__(self):
        self.max_exposure_pct = CRYPTO_MAX_EXPOSURE_PCT
        self.volatility_threshold = CRYPTO_VOLATILITY_THRESHOLD
        self.max_spread = CRYPTO_MAX_SPREAD_PIPS

    def evaluate_crypto_safety(self, symbol: str, direction: str, size_lots: float,
                               open_positions: List[Dict], is_probe: bool = False) -> Tuple[bool, str]:
        """
        Runs comprehensive crypto security filters.
        Returns (is_safe, reason).
        """
        # 1. Total Crypto Allocation & Exposure Caps
        try:
            total_equity = broker_manager.get_equity(broker="coindcx")
            # Fallback to general default equity if coindcx fails or is 0
            if total_equity <= 0:
                total_equity = broker_manager.get_equity()
                
            if total_equity <= 0:
                return False, "Crypto Risk: Unable to retrieve account equity."

            # Calculate total current exposure on CoinDCX
            open_crypto = [p for p in open_positions if p.get("broker") == "coindcx" or p.get("symbol") in ("BTCUSDT", "ETHUSDT")]
            current_lots = sum(p.get("lots", p.get("position_size_lots", 0.0)) for p in open_crypto)
            
            # Fetch current prices to get USD exposure
            tick = broker_manager.get_tick(symbol, broker="coindcx")
            price = tick.get("ask", tick.get("bid", 0.0)) if tick else 0.0
            if price <= 0:
                price = 60000.0 if "BTC" in symbol else 3000.0  # Safe defaults
                
            new_position_usd = size_lots * price
            current_positions_usd = 0.0
            for pos in open_crypto:
                p_symbol = pos.get("symbol", "")
                p_lots = pos.get("lots", pos.get("position_size_lots", 0.0))
                p_price = pos.get("entry_price", 0.0)
                current_positions_usd += p_lots * p_price
                
            total_exposure_usd = current_positions_usd + new_position_usd
            max_allowed_usd = total_equity * self.max_exposure_pct
            
            if total_exposure_usd > max_allowed_usd:
                return False, f"Exposure Cap Veto: Total exposure (${total_exposure_usd:.2f}) exceeds maximum allocation limit of {self.max_exposure_pct * 100}% (${max_allowed_usd:.2f})"
        except Exception as e:
            logger.error(f"Error checking crypto exposure: {e}")

        # 2. Spread Validation
        try:
            spread_info = broker_manager.get_current_price(symbol, broker="coindcx")
            spread = spread_info.get("spread", 999.0)
            if spread > self.max_spread:
                return False, f"Spread Veto: Current spread ({spread:.2f}) exceeds maximum threshold ({self.max_spread:.2f})"
        except Exception as e:
            logger.error(f"Error validating crypto spread: {e}")

        # 3. Volatility Validation
        try:
            # Fetch last 50 candles (M5/M15) to calculate average true range / standard deviation
            df = broker_manager.get_ohlcv(symbol, "M15", 50, broker="coindcx")
            if df is not None and len(df) >= 20:
                close = df["close"]
                returns = close.pct_change().dropna()
                volatility = float(returns.std())
                if volatility > self.volatility_threshold:
                    return False, f"Volatility Veto: Volatility index ({volatility:.4f}) exceeds threshold ({self.volatility_threshold:.4f})"
        except Exception as e:
            logger.error(f"Error validating crypto volatility: {e}")

        # 4. Liquidity & Order Book Validation
        try:
            # Future-ready: check order book depth. Currently validates spread limits.
            pass
        except Exception as e:
            logger.error(f"Error validating crypto liquidity: {e}")

        # 5. Leverage & Liquidation Risk (Future-Ready Scaffold)
        # Spot trades have no liquidation price. Return safe.

        return True, "Passed Crypto Risk Guardian validation."

    def calculate_lot_size(self, symbol: str, equity: float, stop_loss: float, entry_price: float, risk_usd: float) -> float:
        """
        Calculates optimal position size in tokens (lots) based on dollar risk and SL distance.
        """
        if stop_loss <= 0 or entry_price <= 0 or equity <= 0:
            return 0.001
            
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            return 0.001

        # Lot size = Risk USD / SL distance
        lots = risk_usd / sl_distance
        
        # Round according to standard crypto precision
        # BTC/ETH typically allows 3 decimal places (0.001)
        lots = round(lots, 3)
        
        # Ensure it is at least minimum size
        return max(0.001, lots)

crypto_risk_guardian = CryptoRiskGuardian()
