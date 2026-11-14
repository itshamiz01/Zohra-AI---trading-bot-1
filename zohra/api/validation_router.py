"""
╔══════════════════════════════════════════════════════════════════════╗
║         ZOHRA — VALIDATION & MONITORING LAYER API ROUTER             ║
║   REST Endpoints for Backtesting, Paper, Replay, Explain & Health    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Optional, Dict, Any

try:
    from fastapi import APIRouter, Query, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

logger = logging.getLogger("zohra.api.validation")

router = None

if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/api/validation", tags=["Validation & Monitoring Layer"])

    # ─── Pydantic Models ──────────────────────────────────────

    class BacktestRequest(BaseModel):
        symbol: str
        timeframe: str = "H1"
        bars_count: int = 500
        spread: float = 1.2
        slippage: float = 0.5
        commission: float = 3.50
        latency: float = 150.0

    class ReplayLoadRequest(BaseModel):
        preset: str

    class ReplayControlRequest(BaseModel):
        action: str  # play / pause / step_forward / step_backward
        speed: Optional[float] = 1.0
        time: Optional[str] = None # ISO format date

    class PaperOrderRequest(BaseModel):
        symbol: str
        direction: str
        lots: float
        stop_loss: float = 0.0
        take_profit: float = 0.0
        price: float = 0.0

    # ─── Module 1: Backtesting Division ───────────────────────

    @router.post("/backtest")
    async def run_backtest(req: BacktestRequest):
        """Trigger an institutional backtest simulation."""
        try:
            from zohra.validation.backtester import InstitutionalBacktester
            from zohra.brokers.manager import broker_manager
            
            df = broker_manager.get_ohlcv(req.symbol, req.timeframe, count=req.bars_count)
            if df is None:
                raise HTTPException(status_code=400, detail="Failed to fetch backtest historical candles")

            # Simple mock SMA strategy function
            def mock_sma_strategy(data, idx):
                close = data["close"].values
                if len(close) < 20:
                    return None
                ma5 = float(data["close"].rolling(5).mean().iloc[-1])
                ma20 = float(data["close"].rolling(20).mean().iloc[-1])
                
                if ma5 > ma20 and close[-1] > ma5:
                    return {"direction": "LONG", "stop_loss": close[-1]*0.99, "take_profit": close[-1]*1.02}
                elif ma5 < ma20 and close[-1] < ma5:
                    return {"direction": "SHORT", "stop_loss": close[-1]*1.01, "take_profit": close[-1]*0.98}
                return None

            tester = InstitutionalBacktester()
            tester.configure(req.spread, req.slippage, req.commission, req.latency)
            report = tester.run(req.symbol, df, mock_sma_strategy, req.timeframe)
            mc = tester.run_monte_carlo(iterations=100)
            
            return {
                "status": "success",
                "performance": report,
                "monte_carlo": mc
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─── Module 2: Paper Trading Engine ───────────────────────

    @router.get("/paper/portfolio")
    async def get_paper_portfolio():
        """Get virtual portfolio status."""
        try:
            from zohra.validation.paper_engine import paper_engine
            paper_engine.update_open_positions_pnl()
            return {"status": "success", **paper_engine.get_portfolio_status()}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.post("/paper/order")
    async def place_paper_order(req: PaperOrderRequest):
        """Place simulated trade inside virtual portfolio."""
        try:
            from zohra.validation.paper_engine import paper_engine
            res = paper_engine.place_order(
                symbol=req.symbol, direction=req.direction, lots=req.lots,
                stop_loss=req.stop_loss, take_profit=req.take_profit, price=req.price
            )
            return res
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.post("/paper/close/{ticket}")
    async def close_paper_position(ticket: str):
        """Close simulated position inside virtual portfolio."""
        try:
            from zohra.validation.paper_engine import paper_engine
            res = paper_engine.close_position(ticket)
            return res
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Module 3: Market Replay Engine ───────────────────────

    @router.post("/replay/load")
    async def load_replay_preset(req: ReplayLoadRequest):
        """Load a historic crash or event preset for step-playback."""
        try:
            from zohra.validation.replay_engine import replay_engine
            ok = replay_engine.load_preset(req.preset)
            return {"status": "success" if ok else "error", "symbol": replay_engine.symbol}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.post("/replay/control")
    async def control_replay(req: ReplayControlRequest):
        """Step playback timeline or adjust speeds."""
        try:
            from zohra.validation.replay_engine import replay_engine
            
            if req.action == "play":
                replay_engine.play()
                replay_engine.set_speed(req.speed)
                return {"status": "success", "playing": True}
            elif req.action == "pause":
                replay_engine.pause()
                return {"status": "success", "playing": False}
            elif req.action == "step_forward":
                bar = replay_engine.step_forward()
                return {"status": "success", "bar": bar}
            elif req.action == "step_backward":
                bar = replay_engine.step_backward()
                return {"status": "success", "bar": bar}
            elif req.action == "jump" and req.time:
                from datetime import datetime
                dt = datetime.fromisoformat(req.time.replace("Z", ""))
                ok = replay_engine.jump_to_time(dt)
                return {"status": "success" if ok else "error"}
                
            return {"status": "error", "reason": "Invalid action"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Module 4: AI Explainability ──────────────────────────

    @router.get("/explain/{trade_id}")
    async def get_decision_explanation(trade_id: str):
        """Get explanation for a trade decision by ID."""
        try:
            from zohra.validation.explainability import explainability_engine
            res = explainability_engine.get_explanation(trade_id)
            if res:
                return {"status": "success", "explanation": res}
            raise HTTPException(status_code=404, detail="Explanation not found")
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/explain/recent/all")
    async def get_recent_explanations(limit: int = Query(default=20)):
        """List recent decision explanations."""
        try:
            from zohra.validation.explainability import explainability_engine
            return {"status": "success", "explanations": explainability_engine.list_explanations(limit)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Module 5: Broker Health Monitor ──────────────────────

    @router.get("/health")
    async def get_broker_health():
        """Get broker connection status, heartbeat, and scores."""
        try:
            from zohra.validation.broker_monitor import broker_monitor
            res = broker_monitor.poll_all()
            return {"status": "success", "health": res}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ─── Module 6: Trade Replay & Audit ───────────────────────

    @router.get("/audit/{ticket}")
    async def get_trade_audit(ticket: int):
        """Get forensic audit log of a trade ticket."""
        try:
            from zohra.validation.audit_system import audit_system
            res = audit_system.get_audit(ticket)
            if res:
                return {"status": "success", "audit": res}
            raise HTTPException(status_code=404, detail="Audit trail not found")
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @router.get("/audit/list/all")
    async def list_trade_audits(limit: int = Query(default=20)):
        """List audit trails."""
        try:
            from zohra.validation.audit_system import audit_system
            return {"status": "success", "audits": audit_system.list_audits(limit)}
        except Exception as e:
            return {"status": "error", "error": str(e)}
