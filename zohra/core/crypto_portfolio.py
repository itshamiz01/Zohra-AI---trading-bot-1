"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — CRYPTO PORTFOLIO MANAGER                   ║
║            Asset Allocation, Target Weightings & Rebalancing         ║
║                                                                      ║
║  This module manages multi-asset crypto holdings, compares current   ║
║  allocations with targets, and suggests rebalancing actions.         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, Any, List, Optional
from zohra.config.settings import CRYPTO_PORTFOLIO_TARGET_ALLOCATIONS
from zohra.brokers.manager import broker_manager

logger = logging.getLogger("zohra.crypto_portfolio")

class CryptoPortfolioManager:
    """
    Manages asset allocation weights, total value calculations, and rebalancing swaps.
    """

    def __init__(self):
        self.target_allocations = CRYPTO_PORTFOLIO_TARGET_ALLOCATIONS

    def get_portfolio_status(self) -> Dict[str, Any]:
        """
        Retrieves wallet balances, prices, calculates weights, and returns a dashboard-ready dictionary.
        """
        unavailable = {
            "status": "unavailable",
            "total_value_usd": None,
            "assets": [],
            "rebalance_needed": False,
            "suggestions": [],
            "target_allocations": self.target_allocations,
        }
        try:
            if not broker_manager.is_connected(broker="coindcx"):
                return {**unavailable, "reason": "CoinDCX broker is not connected."}

            adapter = broker_manager.get_adapter("coindcx")
            balances = adapter.get_balances() if hasattr(adapter, "get_balances") else {}
            if not balances:
                return {**unavailable, "reason": "No non-zero wallet balances were returned by CoinDCX."}

            portfolio_value = 0.0
            assets_status = []
            
            for asset, qty in balances.items():
                qty = float(qty)
                if qty <= 0:
                    continue
                    
                if asset in ("USDT", "USD"):
                    price = 1.0
                elif asset == "INR":
                    return {
                        **unavailable,
                        "reason": "INR wallet balance cannot be valued in USD without a live FX quote.",
                    }
                else:
                    symbol = f"{asset}USDT"
                    tick = broker_manager.get_tick(symbol, broker="coindcx")
                    price = tick.get("bid", 0.0) if tick else 0.0
                    if price <= 0:
                        return {
                            **unavailable,
                            "reason": f"No current CoinDCX price is available for {asset}.",
                        }
                
                usd_value = qty * price
                portfolio_value += usd_value
                
                assets_status.append({
                    "asset": asset,
                    "quantity": qty,
                    "price_usd": price,
                    "value_usd": usd_value,
                    "weight_pct": 0.0  # calculated below
                })

            # 3. Calculate weights and deviations
            rebalance_needed = False
            for asset_info in assets_status:
                asset = asset_info["asset"]
                val = asset_info["value_usd"]
                weight = (val / portfolio_value) if portfolio_value > 0 else 0.0
                asset_info["weight_pct"] = weight
                
                # Check deviation
                target_key = f"{asset}USDT" if asset not in ("USDT", "USD", "INR") else "CASH"
                target_weight = self.target_allocations.get(target_key, 0.0)
                deviation = abs(weight - target_weight)
                asset_info["target_weight"] = target_weight
                asset_info["deviation"] = deviation
                
                if deviation >= 0.05:  # 5% threshold
                    rebalance_needed = True

            # 4. Compile rebalancing suggestions
            suggestions = []
            if rebalance_needed:
                for asset_info in assets_status:
                    asset = asset_info["asset"]
                    weight = asset_info["weight_pct"]
                    target_key = f"{asset}USDT" if asset not in ("USDT", "USD", "INR") else "CASH"
                    target_w = self.target_allocations.get(target_key, 0.0)
                    
                    if weight < target_w - 0.05:
                        diff_usd = (target_w - weight) * portfolio_value
                        suggestions.append(f"BUY {asset}: Under-allocated by {diff_usd:.2f} USD ({weight*100:.1f}% vs {target_w*100:.1f}%)")
                    elif weight > target_w + 0.05:
                        diff_usd = (weight - target_w) * portfolio_value
                        suggestions.append(f"SELL {asset}: Over-allocated by {diff_usd:.2f} USD ({weight*100:.1f}% vs {target_w*100:.1f}%)")

            return {
                "status": "success",
                "total_value_usd": portfolio_value,
                "assets": assets_status,
                "rebalance_needed": rebalance_needed,
                "suggestions": suggestions,
                "target_allocations": self.target_allocations
            }

        except Exception as e:
            logger.error(f"Error compiling portfolio status: {e}")
            return {**unavailable, "reason": str(e)}

    def evaluate_rebalance_trades(self) -> List[Dict[str, Any]]:
        """
        Translates allocation discrepancies into executable order profiles.
        """
        status = self.get_portfolio_status()
        if status.get("status") != "success":
            return []
        trades = []
        if not status["rebalance_needed"]:
            return trades

        total_val = status["total_value_usd"]
        for asset_info in status["assets"]:
            asset = asset_info["asset"]
            if asset in ("USDT", "USD", "INR"):
                continue
                
            weight = asset_info["weight_pct"]
            target_w = asset_info["target_weight"]
            deviation = target_w - weight  # positive means buy, negative means sell
            
            if abs(deviation) >= 0.05:
                direction = "BUY" if deviation > 0 else "SELL"
                trade_val_usd = abs(deviation) * total_val
                
                # Fetch price
                price = asset_info["price_usd"]
                lots = trade_val_usd / price if price > 0 else 0.0
                lots = round(lots, 3)
                
                if lots > 0.001:
                    trades.append({
                        "symbol": f"{asset}USDT",
                        "direction": direction,
                        "lots": lots,
                        "comment": f"REBALANCE_{asset}"
                    })
        return trades

crypto_portfolio_manager = CryptoPortfolioManager()
