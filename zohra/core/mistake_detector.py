"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — MISTAKE DETECTION ENGINE                   ║
║         Automated Trade Execution & Parameter Audit                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger("zohra.learning.mistake")

class MistakeDetector:
    """
    Analyzes closed trade metrics against initial trade parameters and risk rules
    to identify execution mistakes (e.g., chasing entry, widening stops, overtrading).
    """
    def analyze_trade_for_mistakes(self, trade: Dict[str, Any]) -> List[Dict[str, Any]]:
        mistakes = []
        
        # Extract parameters
        symbol = trade.get("symbol", "")
        direction = trade.get("direction", "LONG")
        entry = trade.get("entry_price", 0.0)
        sl = trade.get("stop_loss", 0.0)
        tp = trade.get("take_profit", 0.0)
        pnl = trade.get("pnl_usd", 0.0)
        
        # 1. Check for Chasing Price (Entry too far from proposed entry)
        # Assuming we can compare the fill price with the requested price if available
        requested = trade.get("requested_price", entry)
        if requested > 0 and entry > 0:
            slippage = abs(entry - requested)
            # If slippage is excessive (> 5 pips) it could indicate chasing market orders
            point_multiplier = 10000.0 if "JPY" not in symbol and symbol != "XAUUSD" else 100.0
            slippage_pips = slippage * point_multiplier
            
            if slippage_pips >= 4.0:
                mistakes.append({
                    "type": "Chasing Price / High Slippage",
                    "severity": "MINOR",
                    "description": f"Trade filled {slippage_pips:.1f} pips away from requested entry. Indicates possible execution lag or market order chasing."
                })

        # 2. Check for Widening Stop Loss (Post-entry risk increase)
        # (If the final closed trade stop loss was adjusted further away than initial)
        initial_sl = trade.get("initial_stop_loss", sl)
        if initial_sl > 0 and sl > 0:
            if direction == "LONG" and sl < initial_sl:
                mistakes.append({
                    "type": "Widen Stop Loss",
                    "severity": "CRITICAL",
                    "description": "Stop loss was moved further down, increasing trade risk post-entry."
                })
            elif direction == "SHORT" and sl > initial_sl:
                mistakes.append({
                    "type": "Widen Stop Loss",
                    "severity": "CRITICAL",
                    "description": "Stop loss was moved further up, increasing trade risk post-entry."
                })

        # 3. Check for Poor Risk-to-Reward Ratio
        if entry > 0 and sl > 0 and tp > 0:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rrr = reward / (risk + 1e-9)
            if rrr < 1.0:
                mistakes.append({
                    "type": "Poor RRR",
                    "severity": "MAJOR",
                    "description": f"Trade entered with an unfavorable Risk-to-Reward ratio ({rrr:.2f}R). Minimum target should be >= 1.5R."
                })

        # 4. Check for Holding Losses (Stop loss bypassed or not set)
        if sl == 0:
            mistakes.append({
                "type": "No Stop Loss",
                "severity": "CRITICAL",
                "description": "Trade executed without a stop loss. Extremely high capital risk."
            })

        return mistakes

# Singleton
mistake_detector = MistakeDetector()
