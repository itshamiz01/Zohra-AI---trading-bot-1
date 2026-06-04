"""
Risk Management Engine
Position sizing, exposure limits, circuit breakers.
"""

import math
from datetime import datetime
from typing import Optional, Dict, List
from config import (
    RISK_PER_TRADE_PCT, MAX_OPEN_POSITIONS, MAX_DAILY_LOSS_PCT,
    MAX_MONTHLY_LOSS_PCT, MIN_LOT_SIZE, MAX_LOT_SIZE, LOT_STEP,
    PAIRS, STATE
)
from database import db

class RiskManager:
    """
    Enforces all risk rules before any trade is executed.
    """

    def __init__(self):
        self.rules = {
            "max_positions": MAX_OPEN_POSITIONS,
            "risk_per_trade": RISK_PER_TRADE_PCT,
            "daily_loss_limit": MAX_DAILY_LOSS_PCT,
            "monthly_loss_limit": MAX_MONTHLY_LOSS_PCT
        }

    def can_trade(self, equity: float, symbol: str, 
                  current_positions: List[Dict]) -> tuple[bool, str]:
        """
        Check if trading is allowed.
        Returns (allowed, reason).
        """
        # 1. Global trading enabled
        if not STATE.trading_enabled:
            return False, "Trading manually disabled"

        # 2. Daily loss limit
        daily_loss_pct = abs(STATE.daily_pnl) / equity if equity > 0 else 0
        if STATE.daily_pnl < 0 and daily_loss_pct >= MAX_DAILY_LOSS_PCT:
            return False, f"Daily loss limit hit: {daily_loss_pct*100:.1f}%"

        # 3. Monthly loss limit
        monthly_loss_pct = abs(STATE.monthly_pnl) / equity if equity > 0 else 0
        if STATE.monthly_pnl < 0 and monthly_loss_pct >= MAX_MONTHLY_LOSS_PCT:
            return False, f"Monthly loss limit hit: {monthly_loss_pct*100:.1f}%"

        # 4. Max open positions
        if len(current_positions) >= MAX_OPEN_POSITIONS:
            return False, f"Max positions ({MAX_OPEN_POSITIONS}) reached"

        # 5. Correlation check - don't add same-direction trade on correlated pair
        # Simplified: check if we already have position in same direction on any pair
        for pos in current_positions:
            if pos["symbol"] == symbol:
                return False, f"Already have position in {symbol}"

        # 6. Weekend check (Forex closed Friday 5pm - Sunday 5pm EST)
        from datetime import datetime
        now = datetime.utcnow()
        weekday = now.weekday()
        hour = now.hour

        # Friday after 9pm UTC (5pm EST) to Sunday 9pm UTC
        if weekday == 4 and hour >= 21:
            return False, "Weekend - Forex market closed"
        if weekday == 5:
            return False, "Weekend - Forex market closed"
        if weekday == 6 and hour < 21:
            return False, "Weekend - Forex market closed"

        return True, "OK"

    def calculate_position_size(self, equity: float, entry: float,
                               stop: float, symbol: str) -> int:
        """
        Calculate position size in units (1 lot = 100,000 units).
        Lot size is snapped to LOT_STEP and clamped to broker limits.
        Risk = |entry - stop| * lots * 100,000 = equity * risk_pct
        """
        risk_amount = equity * RISK_PER_TRADE_PCT
        price_risk  = abs(entry - stop)

        if price_risk == 0:
            return 0

        # Calculate ideal lot size
        lots = risk_amount / (price_risk * 100_000)

        # Snap to LOT_STEP and clamp
        lots = round(round(lots / LOT_STEP) * LOT_STEP, 2)
        lots = max(MIN_LOT_SIZE, min(lots, MAX_LOT_SIZE))

        # Return as units so scheduler/DB code stays unchanged
        units = int(lots * 100_000)
        return units

    def validate_signal(self, signal: Dict, equity: float, 
                       current_positions: List[Dict]) -> Optional[Dict]:
        """
        Full validation pipeline for a signal.
        Returns validated trade dict or None.
        """
        symbol = signal.get("symbol", "")

        # Check if we can trade
        allowed, reason = self.can_trade(equity, symbol, current_positions)
        if not allowed:
            db.log_system("INFO", f"Signal rejected for {symbol}: {reason}")
            return None

        # Calculate position size
        entry = signal["entry"]
        stop = signal["stop"]
        units = self.calculate_position_size(equity, entry, stop, symbol)

        min_units = int(MIN_LOT_SIZE * 100_000)
        if units < min_units:
            db.log_system("INFO", f"Signal rejected: position size too small ({units} units / {units/100_000:.2f} lots)")
            return None

        # Calculate actual risk
        price_risk = abs(entry - stop)
        risk_usd = price_risk * units

        # Validate R/R ratio
        target = signal["target"]
        reward = abs(target - entry)
        risk_reward = reward / price_risk if price_risk > 0 else 0

        if risk_reward < 1.5:
            db.log_system("INFO", f"Signal rejected: R/R too low ({risk_reward:.1f})")
            return None

        return {
            "trade_id": f"{symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "symbol": symbol,
            "direction": signal["direction"],
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "position_size": units,
            "risk_usd": risk_usd,
            "risk_reward": risk_reward,
            "ema_fast": signal["ema_fast"],
            "ema_slow": signal["ema_slow"],
            "atr": signal["atr"]
        }

    def update_pnl_state(self, pnl: float):
        """Update daily/monthly P&L tracking"""
        STATE.daily_pnl += pnl
        STATE.monthly_pnl += pnl

    def reset_daily(self):
        """Reset daily stats (call at market open)"""
        STATE.daily_pnl = 0
        STATE.trades_today = 0

    def reset_monthly(self):
        """Reset monthly stats"""
        STATE.monthly_pnl = 0

    def get_status(self) -> Dict:
        """Current risk status for reporting"""
        return {
            "trading_enabled": STATE.trading_enabled,
            "daily_pnl": round(STATE.daily_pnl, 2),
            "monthly_pnl": round(STATE.monthly_pnl, 2),
            "trades_today": STATE.trades_today,
            "max_daily_loss": f"{MAX_DAILY_LOSS_PCT*100:.0f}%",
            "max_monthly_loss": f"{MAX_MONTHLY_LOSS_PCT*100:.0f}%",
            "risk_per_trade": f"{RISK_PER_TRADE_PCT*100:.0f}%"
        }

# Singleton instance
risk_manager = RiskManager()
