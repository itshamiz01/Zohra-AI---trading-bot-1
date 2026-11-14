"""
╔══════════════════════════════════════════════════════════════════════╗
║         ZOHRA — INTELLIGENCE LAYER API ROUTER                        ║
║   REST Endpoints for Portfolio, Regime, Macro, Cross-Market, etc.   ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional

try:
    from fastapi import APIRouter, Query, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger("zohra.api.intelligence")

router = None

if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/api/intelligence", tags=["Intelligence Layer"])

    class OptimizeRequest(BaseModel):
        strategy_name: str
        params: dict = {}

    # ─── Portfolio Intelligence ────────────────────────────────

    @router.get("/portfolio")
    async def get_portfolio_intelligence():
        """Get portfolio health, allocations, risk metrics."""
        try:
            from zohra.intelligence.portfolio_intelligence import portfolio_intel
            return {"status": "success", **portfolio_intel.get_snapshot()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/portfolio/stress-test")
    async def get_stress_test(scenario: Optional[str] = None):
        """Run stress test on portfolio."""
        try:
            from zohra.intelligence.portfolio_intelligence import portfolio_intel
            results = portfolio_intel.stress_test(scenario)
            return {"status": "success", "scenarios": results}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Market Regime ─────────────────────────────────────────

    @router.get("/regime/{symbol}")
    async def get_regime(symbol: str):
        """Get current market regime for a symbol."""
        try:
            from zohra.intelligence.regime_engine import regime_engine
            return {"status": "success", **regime_engine.get_regime(symbol)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Macro Intelligence ────────────────────────────────────

    @router.get("/macro/upcoming")
    async def get_upcoming_macro(hours: int = Query(default=4)):
        """Get upcoming macro events."""
        try:
            from zohra.intelligence.macro_intelligence import macro_engine
            events = macro_engine.get_upcoming_events(hours)
            return {"status": "success", "events": [e.to_dict() for e in events]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/macro/summary")
    async def get_macro_summary():
        """Get macro landscape summary."""
        try:
            from zohra.intelligence.macro_intelligence import macro_engine
            return {"status": "success", **macro_engine.get_macro_summary()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/macro/clearance/{symbol}")
    async def check_macro_clearance(symbol: str):
        """Check if trading is safe given macro events."""
        try:
            from zohra.intelligence.macro_intelligence import macro_engine
            return {"status": "success", **macro_engine.check_trade_clearance(symbol)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Cross-Market Intelligence ─────────────────────────────

    @router.get("/cross-market")
    async def get_cross_market():
        """Get cross-market correlation and flow data."""
        try:
            from zohra.intelligence.cross_market import cross_market_engine
            return {"status": "success", **cross_market_engine.get_intel()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/cross-market/compare")
    async def compare_assets(asset_a: str = Query(...), asset_b: str = Query(...)):
        """Compare two assets."""
        try:
            from zohra.intelligence.cross_market import cross_market_engine
            return {"status": "success", **cross_market_engine.compare_assets(asset_a, asset_b)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Multi-Timeframe Analysis ──────────────────────────────

    @router.get("/mtf/{symbol}")
    async def get_mtf_analysis(symbol: str):
        """Get multi-timeframe alignment for a symbol."""
        try:
            from zohra.intelligence.multi_timeframe import mtf_engine
            result = mtf_engine.analyze(symbol)
            return {"status": "success", **result.to_dict()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Smart Money Analysis ──────────────────────────────────

    @router.get("/smc/{symbol}")
    async def get_smc_analysis(symbol: str, timeframe: str = Query(default="M15")):
        """Get smart money analysis for a symbol."""
        try:
            from zohra.intelligence.smart_money import smc_engine
            from zohra.brokers.manager import broker_manager
            df = broker_manager.get_ohlcv(symbol, timeframe, count=100)
            if df is None:
                return {"status": "error", "error": "Could not fetch data"}
            result = smc_engine.analyze(df, symbol, timeframe)
            return {"status": "success", **result.to_dict()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Strategy Marketplace ──────────────────────────────────

    @router.get("/strategies")
    async def list_strategies(category: Optional[str] = None):
        """List strategies in the marketplace."""
        try:
            from zohra.intelligence.strategy_marketplace import strategy_marketplace
            strategies = strategy_marketplace.list_all(category=category)
            return {"status": "success", "strategies": [s.to_dict() for s in strategies]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/strategies/top")
    async def get_top_strategy():
        """Get the highest-rated strategy."""
        try:
            from zohra.intelligence.strategy_marketplace import strategy_marketplace
            top = strategy_marketplace.get_top_strategy()
            return {"status": "success", "strategy": top.to_dict() if top else None}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/strategies/summary")
    async def get_marketplace_summary():
        """Get marketplace summary."""
        try:
            from zohra.intelligence.strategy_marketplace import strategy_marketplace
            return {"status": "success", **strategy_marketplace.get_summary()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Strategy Optimizer ────────────────────────────────────

    @router.get("/optimizer/history")
    async def get_optimizer_history(strategy: Optional[str] = None):
        """Get optimization run history."""
        try:
            from zohra.intelligence.strategy_optimizer import strategy_optimizer
            return {"status": "success", "history": strategy_optimizer.get_history(strategy)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.post("/optimize")
    async def trigger_optimization(req: OptimizeRequest):
        """Trigger a quick optimization for a strategy."""
        try:
            from zohra.intelligence.strategy_optimizer import strategy_optimizer
            result = strategy_optimizer.quick_optimize(req.strategy_name, req.params)
            return {"status": "success", **result.to_dict()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Decision Pipeline ─────────────────────────────────────

    @router.get("/pipeline/last")
    async def get_last_decision(symbol: Optional[str] = None):
        """Get the last pipeline decision."""
        try:
            from zohra.intelligence.decision_pipeline import decision_pipeline
            return {"status": "success", **decision_pipeline.get_last_decision(symbol)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/pipeline/all")
    async def get_all_decisions():
        """Get latest decisions across all symbols."""
        try:
            from zohra.intelligence.decision_pipeline import decision_pipeline
            return {"status": "success", "decisions": decision_pipeline.get_all_decisions()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.post("/pipeline/evaluate/{symbol}")
    async def evaluate_symbol(symbol: str):
        """Run the full intelligence pipeline for a symbol."""
        try:
            from zohra.intelligence.decision_pipeline import decision_pipeline
            result = decision_pipeline.evaluate(symbol)
            return {"status": "success", **result.to_dict()}
        except Exception as e:
            return {"status": "error", "error": str(e)}
