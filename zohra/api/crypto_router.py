"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — CRYPTO REST API ROUTER                     ║
║         API Endpoints for Portfolio, status, and Intelligence        ║
║                                                                      ║
║  This module exposes HTTP interfaces for the living dashboard to     ║
║  monitor crypto wallet balances, macro dominance, and active deals.  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException

from zohra.brokers.manager import broker_manager
from zohra.core.crypto_portfolio import crypto_portfolio_manager
from zohra.core.crypto_intelligence import crypto_intelligence
from zohra.core.crypto_engine import crypto_engine

router = APIRouter(prefix="/api/crypto", tags=["Crypto Market Engine"])
logger = logging.getLogger("zohra.crypto_router")

@router.get("/status")
def get_engine_status() -> Dict[str, Any]:
    """Get active state of the Zohra Crypto Market Engine."""
    return {
        "running": crypto_engine.running,
        "active_pairs": crypto_engine.crypto_pairs,
        "registered_strategies": list(crypto_engine.strategies.keys()),
        "broker": "coindcx"
    }

@router.get("/portfolio")
def get_portfolio() -> Dict[str, Any]:
    """Get asset allocation balances and rebalancing status."""
    try:
        return crypto_portfolio_manager.get_portfolio_status()
    except Exception as e:
        logger.error(f"API portfolio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/intelligence")
def get_market_intelligence() -> Dict[str, Any]:
    """Get macro correlations, dominance levels, and whale tracking indices."""
    try:
        return crypto_intelligence.update_intelligence_metrics()
    except Exception as e:
        logger.error(f"API intelligence error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades/open")
def get_open_crypto_positions() -> List[Dict[str, Any]]:
    """Get currently active positions executed on CoinDCX."""
    try:
        return broker_manager.get_open_positions(broker="coindcx")
    except Exception as e:
        logger.error(f"API active trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rebalance")
def trigger_manual_rebalance() -> Dict[str, Any]:
    """Manually forces checking target weights and suggest swaps."""
    try:
        trades = crypto_portfolio_manager.evaluate_rebalance_trades()
        return {
            "rebalance_triggered": len(trades) > 0,
            "trades_generated": trades
        }
    except Exception as e:
        logger.error(f"API rebalance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
