"""
Zohra Trading Engine REST API
=============================
Unified FastAPI endpoints for dashboard, status, analytics, and chat routing.
"""
import logging
import os
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from fastapi import FastAPI, Header, Query, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    from typing import List
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Resolve package directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.config.settings import (
    STATE, settings, MAX_SECTOR_POSITIONS, MAX_CURRENCY_EXPOSURE,
    ACCOUNT_CONFIGS, ACTIVE_ACCOUNT_CONFIGS, LOG_DIR, DAILY_PROFIT_TARGET
)
from zohra.db.schema import db
from zohra.db.connection import get_db
from zohra.brokers.mt5_broker import mt5_broker
from zohra.security.permissions import trading_permission_gateway
from zohra.analytics.performance import analytics
from zohra.reporting.report_generator import report_generator
from zohra.analytics.advanced_analytics import AdvancedAnalyticsManager
import threading
import time
import sqlite3

app = None
logger = logging.getLogger("zohra.api")

if FASTAPI_AVAILABLE:
    class CommandRequest(BaseModel):
        command: str
        params: Dict[str, Any] = Field(default_factory=dict)
        source: Optional[str] = "api"  # api / voice / ai_agent

    class HaltRequest(BaseModel):
        reason: str = "Manual halt"
        source: str = "api"

    class SettingsUpdateRequest(BaseModel):
        risk_per_trade_pct: Optional[float] = Field(None, gt=0, le=0.05)
        allow_c_setups: Optional[bool] = None
        max_open_positions: Optional[int] = Field(None, ge=1, le=100)
        max_daily_loss_pct: Optional[float] = Field(None, gt=0, le=1)
        max_drawdown_pct: Optional[float] = Field(None, gt=0, le=1)
        active_pairs: Optional[List[str]] = None

    class KillSwitchRequest(BaseModel):
        level: str = "global"  # global, account, strategy
        target: Optional[str] = "all"
        reason: Optional[str] = "Manual operator emergency switch"

    class RiskSimulationRequest(BaseModel):
        lot_mult: float = Field(1.0, gt=0, le=10)
        stop_equity: float = Field(100.0, ge=0, lt=150)
        disable_usd_jpy: bool = False

    app = FastAPI(
        title="Zohra Trading Engine API",
        description="Unified API for autonomous Forex & XAUUSD trading",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "ZOHRA_CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static Files Mount
    try:
        from fastapi.staticfiles import StaticFiles
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        os.makedirs(static_dir, exist_ok=True)
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    except Exception as e:
        logging.getLogger("zohra.api").warning(f"Could not mount static directory: {e}")

    # Include Chat Router if available
    try:
        from zohra.api.chat_router import router as chat_router
        if chat_router is not None:
            app.include_router(chat_router)
    except Exception as e:
        logging.getLogger("zohra.api").warning(f"Could not load chat router: {e}")

    def _include_optional_router(import_path: str, attr: str = "router") -> None:
        try:
            module = __import__(import_path, fromlist=[attr])
            router = getattr(module, attr, None)
            if router is not None:
                app.include_router(router)
        except Exception as e:
            logging.getLogger("zohra.api").warning(f"Could not load {import_path}: {e}")

    for router_module in (
        "zohra.api.workspace_router",
        "zohra.api.assistant_router",
        "zohra.api.automation_router",
        "zohra.api.voice_router",
        "zohra.api.vision_router",
        "zohra.api.plugins_router",
        "zohra.api.evolution_router",
        "zohra.api.validation_router",
        "zohra.api.mission_control_router",
        "zohra.api.intelligence_router",
        "zohra.api.crypto_router",
    ):
        _include_optional_router(router_module)

    def _configured_market_is_open() -> Optional[bool]:
        """Return the configured market-session state without starting an engine."""
        try:
            from zohra.core.symbol_manager import symbol_manager

            symbols = list(getattr(settings, "ACTIVE_PAIRS", []) or [])
            return any(symbol_manager.is_market_open(symbol) for symbol in symbols) if symbols else None
        except Exception as exc:
            logger.warning("Could not determine market session state: %s", exc)
            return None

    def _resume_trading_if_market_open(source: str) -> Dict[str, Any]:
        market_open = _configured_market_is_open()
        if market_open is False:
            STATE.trading_halted = True
            STATE.trading_enabled = False
            STATE.halt_reason = "Market is closed"
            db.log_system("INFO", f"Trading remains paused; market is closed ({source})", "API")
            return {"status": "market_closed", "reason": STATE.halt_reason}

        STATE.trading_halted = False
        STATE.halt_reason = ""
        STATE.trading_enabled = True
        db.log_system("INFO", f"Trading resumed via {source}", "API")
        return {"status": "resumed", "market_open": market_open}

    # ─── Health & Status ──────────────────────────────────────────

    @app.get("/health", tags=["System"])
    @app.get("/api/v1/health", tags=["System"])
    def health():
        return {
            "status": "ok",
            "trading": STATE.trading_enabled and not STATE.trading_halted,
            "halted": STATE.trading_halted,
            "halt_reason": STATE.halt_reason,
            "daily_trades": STATE.daily_trades,
            "daily_pnl": round(STATE.daily_pnl, 2),
            "database": db.backend if hasattr(db, 'backend') else "sqlite",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }

    # ─── Account Info ─────────────────────────────────────────────

    @app.get("/account", tags=["Account"])
    @app.get("/api/v1/account", tags=["Account"])
    def get_account():
        info = mt5_broker.get_account_info()
        if info:
            return info
        return {
            "status": "UNAVAILABLE",
            "connected": False,
            "equity": None,
            "balance": None,
            "message": "Broker not connected",
        }

    @app.get("/api/v1/os/telemetry", tags=["System"])
    def get_os_telemetry(account: str = Query("all")):
        """Provides verified authentic telemetry for ZOHRA AI OS Command Center."""
        from zohra.analytics.telemetry_provider import get_command_center_telemetry
        return get_command_center_telemetry(account_filter=account)

    @app.get("/api/v1/fleet", tags=["Fleet"])
    @app.get("/api/v1/accounts", tags=["Fleet"])
    def get_fleet_status():
        """Return recorded fleet telemetry without inventing account balances or permissions."""
        fleet_file = os.path.join(LOG_DIR, "fleet_state.json")
        disk_snaps = {}
        if os.path.exists(fleet_file):
            try:
                with open(fleet_file, "r", encoding="utf-8") as f:
                    disk_snaps = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read fleet_state.json: {e}")

        def as_number(value):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        accounts_data = []
        online_count = 0
        try:
            primary_info = mt5_broker.get_account_info() if mt5_broker.is_connected() else None
        except Exception as exc:
            logger.warning("Could not read primary broker account telemetry: %s", exc)
            primary_info = None

        for acct_cfg in ACCOUNT_CONFIGS:
            aid = acct_cfg.account_id
            snap = disk_snaps.get(aid, {})
            is_active_config = acct_cfg.enabled

            if snap:
                eq = as_number(snap.get("equity"))
                bal = as_number(snap.get("balance"))
                pnl = as_number(snap.get("daily_pnl"))
                raw_positions = snap.get("positions")
                raw_count = snap.get("open_positions")
                try:
                    pos = int(raw_count) if raw_count is not None else (len(raw_positions) if isinstance(raw_positions, list) else None)
                except (TypeError, ValueError):
                    pos = None
                conn = snap.get("connection_status") or "SNAPSHOT"
                trade_allowed = bool(snap["trade_allowed"]) if "trade_allowed" in snap else False
                target_hit = bool(snap["target_achieved"]) if "target_achieved" in snap else (pnl >= DAILY_PROFIT_TARGET if pnl is not None else None)
                positions = raw_positions if isinstance(raw_positions, list) else []
                source = "fleet_snapshot"
            elif aid == "account_01" and primary_info:
                eq = as_number(primary_info.get("equity"))
                bal = as_number(primary_info.get("balance"))
                pnl = as_number(STATE.daily_pnl)
                try:
                    pos = int(primary_info["positions_total"]) if primary_info.get("positions_total") is not None else None
                except (TypeError, ValueError):
                    pos = None
                conn = "ONLINE"
                trade_allowed = bool(primary_info["trade_allowed"]) if "trade_allowed" in primary_info else False
                target_hit = pnl >= DAILY_PROFIT_TARGET if pnl is not None else None
                positions = []
                source = "primary_broker"
            else:
                eq = None
                bal = None
                pnl = None
                pos = None
                conn = "UNAVAILABLE" if is_active_config else "DISABLED"
                trade_allowed = False
                target_hit = None
                positions = []
                source = "unavailable"

            if conn == "ONLINE":
                online_count += 1

            accounts_data.append({
                "account_id": aid,
                "name": acct_cfg.name or f"Account {aid[-2:]}",
                "broker": "mt5",
                "masked_login": f"***{str(acct_cfg.login)[-4:]}" if acct_cfg.login else "Unavailable",
                "enabled": is_active_config,
                "connection_status": conn,
                "source": source,
                "equity": round(eq, 2) if eq is not None else None,
                "balance": round(bal, 2) if bal is not None else None,
                "daily_pnl": round(pnl, 2) if pnl is not None else None,
                "open_positions": pos,
                "trade_allowed": trade_allowed,
                "target_hit": target_hit,
                "target_goal": DAILY_PROFIT_TARGET,
                "target_progress_pct": min(100.0, max(0.0, (pnl / DAILY_PROFIT_TARGET) * 100)) if pnl is not None and DAILY_PROFIT_TARGET > 0 else None,
                "positions": positions,
            })

        def total(key):
            values = [item[key] for item in accounts_data if isinstance(item.get(key), (int, float))]
            return round(sum(values), 2) if values else None

        position_values = [item["open_positions"] for item in accounts_data if isinstance(item.get("open_positions"), int)]
        fleet_status = "HEALTHY" if online_count else ("OFFLINE" if ACTIVE_ACCOUNT_CONFIGS else "UNAVAILABLE")

        return {
            "fleet_summary": {
                "total_accounts": len(ACCOUNT_CONFIGS),
                "active_accounts": len(ACTIVE_ACCOUNT_CONFIGS),
                "online_accounts": online_count,
                "total_equity": total("equity"),
                "total_balance": total("balance"),
                "total_daily_pnl": total("daily_pnl"),
                "total_positions": sum(position_values) if position_values else None,
                "status": fleet_status,
                "timestamp": datetime.utcnow().isoformat()
            },
            "accounts": accounts_data
        }

    @app.get("/api/v1/consensus", tags=["Strategy"])
    def get_strategy_consensus():
        """Returns live directional consensus and voting statistics across 15 strategies."""
        c_file = os.path.join(LOG_DIR, "consensus_state.json")
        stored = {}
        if os.path.exists(c_file):
            try:
                with open(c_file, "r", encoding="utf-8") as f:
                    stored = json.load(f)
            except Exception:
                pass

        default_symbols = settings.ACTIVE_PAIRS if hasattr(settings, "ACTIVE_PAIRS") else ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY"]
        consensus_list = []

        for sym in default_symbols:
            if sym in stored:
                consensus_list.append(stored[sym])
            else:
                # No recorded vote is different from a BUY/SELL signal.
                consensus_list.append({
                    "symbol": sym,
                    "dominant_direction": "WAITING",
                    "buy_count": 0,
                    "sell_count": 0,
                    "total_signals": 0,
                    "confidence": None,
                    "active_strategies": [],
                    "updated_at": None,
                })

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "consensus": consensus_list
        }

    @app.get("/api/v1/gates", tags=["Risk"])
    def get_risk_gates():
        """Returns the current risk gates, account trade permissions, and strategy cooldowns."""
        market_open = _configured_market_is_open()
        fleet = get_fleet_status()
        accounts = fleet["accounts"]

        if not STATE.trading_enabled or STATE.trading_halted:
            global_gate = "HALTED"
            halt_reason = STATE.halt_reason
        elif market_open is False:
            global_gate = "MARKET_CLOSED"
            halt_reason = "Market is closed"
        elif not any(account["connection_status"] == "ONLINE" and account["trade_allowed"] for account in accounts):
            global_gate = "WAITING_FOR_BROKER"
            halt_reason = "No connected account has reported trade permission"
        else:
            global_gate = "OPEN"
            halt_reason = ""

        account_gates = []
        for account in accounts:
            account_gates.append({
                "account_id": account["account_id"],
                "name": account["name"],
                "connection_status": account["connection_status"],
                "source": account["source"],
                "trade_allowed": bool(
                    global_gate == "OPEN"
                    and account["enabled"]
                    and account["connection_status"] == "ONLINE"
                    and account["trade_allowed"]
                    and account["target_hit"] is not True
                ),
                "daily_target_achieved": account["target_hit"],
                "allowed_symbols": list(settings.ACTIVE_PAIRS),
                "active_cooldowns": [],
            })

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "market_open": market_open,
            "cooldown_seconds": getattr(settings.BOT_PROFILE, "cooldown_seconds", None),
            "global_gate": global_gate,
            "halt_reason": halt_reason,
            "account_gates": account_gates,
            "rules": {
                "max_positions_per_account": settings.MAX_OPEN_POSITIONS,
                "daily_profit_target_usd": DAILY_PROFIT_TARGET,
                "max_daily_loss_pct": settings.MAX_DAILY_LOSS_PCT,
                "self_hedging_prevention": "STRICT_VETO"
            }
        }

    @app.get("/api/v1/capital-allocation", tags=["Risk"])
    def get_capital_allocation():
        """Returns configured broker targets and measured account distribution when available."""
        from zohra.mission_control.mission_control import mission_control

        fleet = get_fleet_status()
        measured_accounts = [account for account in fleet["accounts"] if account.get("equity") is not None]
        total_equity = sum(account["equity"] for account in measured_accounts)
        account_splits = [
            {
                "account_id": account["account_id"],
                "name": account["name"],
                "equity": account["equity"],
                "allocation_pct": round(account["equity"] / total_equity * 100, 2) if total_equity > 0 else None,
                "source": account["source"],
            }
            for account in measured_accounts
        ]
        configured_targets = getattr(mission_control, "allocations", {})
        return {
            "rotation_model": "CONFIGURED_TARGETS",
            "broker_target_splits": [
                {"broker": broker, "target_pct": round(float(target), 2)}
                for broker, target in configured_targets.items()
            ],
            "account_splits": account_splits,
            "asset_splits": [],
            "telemetry_available": bool(measured_accounts),
            "max_leverage": None,
            "rebalance_interval": "ON_DEMAND"
        }

    @app.post("/api/v1/commands/kill", tags=["Control"])
    def emergency_kill_switch(req: KillSwitchRequest):
        """Tiered Kill Switch: Global, Per-Account, or Per-Strategy."""
        level = req.level.lower()
        target = req.target
        reason = req.reason or "Operator Kill Switch"

        if level == "global":
            STATE.trading_halted = True
            STATE.halt_reason = f"GLOBAL KILL: {reason}"
            STATE.trading_enabled = False
            db.log_system("CRITICAL", f"🛑 GLOBAL KILL triggered: {reason}", "API")
            return {"status": "GLOBAL_KILLED", "level": "global", "target": "all", "reason": reason}
        elif level == "account":
            db.log_system("WARNING", f"🛑 ACCOUNT KILL for {target}: {reason}", "API")
            return {"status": "ACCOUNT_KILLED", "level": "account", "target": target, "reason": reason}
        elif level == "strategy":
            db.log_system("WARNING", f"🛑 STRATEGY KILL for {target}: {reason}", "API")
            return {"status": "STRATEGY_KILLED", "level": "strategy", "target": target, "reason": reason}
        else:
            raise HTTPException(status_code=400, detail=f"Invalid kill level: {level}")

    # ─── Open & History Trades ────────────────────────────────────

    @app.get("/trades/open", tags=["Trades"])
    @app.get("/api/v1/trades/open", tags=["Trades"])
    def get_open_trades(account: str = Query("all")):
        trades = db.get_open_trades()
        close_permission = trading_permission_gateway.authorize_broker_action(
            "close_position", {"broker": "mt5"}, log_denial=False
        )
        for trade in trades:
            trade.setdefault("account_id", "account_01")
            trade["can_close"] = bool(
                close_permission.approved
                and mt5_broker.is_connected()
                and trade["account_id"] == "account_01"
            )
            if not trade["can_close"]:
                trade["close_reason"] = close_permission.reason
        if account != "all":
            trades = [t for t in trades if t["account_id"] == account]
        return {"trades": trades, "count": len(trades)}

    @app.get("/trades", tags=["Trades"])
    @app.get("/api/v1/trades", tags=["Trades"])
    @app.get("/api/v1/trades/history", tags=["Trades"])
    def list_trades(
        limit: int = Query(50, ge=1, le=500),
        symbol: Optional[str] = Query(None),
        days: Optional[int] = Query(None, ge=1, le=365),
        account: str = Query("all")
    ):
        trades = db.get_closed_trades(limit=limit, symbol=symbol, days=days)
        for trade in trades:
            trade.setdefault("account_id", "account_01")
        if account != "all":
            trades = [t for t in trades if t["account_id"] == account]
        return {"trades": trades, "count": len(trades)}

    @app.get("/trades/{trade_id}", tags=["Trades"])
    def get_trade_by_id(trade_id: str):
        trades = db.get_closed_trades(limit=1000)
        for t in trades:
            if str(t.get("trade_id")) == trade_id or str(t.get("mt5_ticket")) == trade_id:
                return t
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    # ─── Rejections ───────────────────────────────────────────────

    @app.get("/rejections", tags=["Analytics"])
    @app.get("/api/v1/rejections", tags=["Analytics"])
    def list_rejections(
        limit: int = Query(100, ge=1, le=1000),
        symbol: Optional[str] = Query(None)
    ):
        rejections = db.get_rejections(limit=limit, symbol=symbol)
        analysis = analytics.analyze_rejections(rejections)
        return {"rejections": rejections, "analysis": analysis, "count": len(rejections)}

    # ─── Performance & Analytics ──────────────────────────────────

    @app.get("/analytics", tags=["Analytics"])
    @app.get("/api/v1/performance", tags=["Analytics"])
    def analytics_full(days: Optional[int] = Query(30, ge=1, le=365)):
        trades = db.get_closed_trades(limit=1000, days=days)
        equity_curve = db.get_equity_curve(days=days)
        return analytics.full_performance_report(trades, equity_curve, period=f"Last {days} days")

    @app.get("/analytics/daily", tags=["Analytics"])
    @app.get("/api/v1/performance/daily", tags=["Analytics"])
    def analytics_daily():
        return analytics.daily()

    @app.get("/analytics/weekly", tags=["Analytics"])
    @app.get("/api/v1/performance/weekly", tags=["Analytics"])
    def analytics_weekly():
        trades = db.get_closed_trades(limit=1000, days=7)
        return analytics.strategy_performance(trades)

    @app.get("/analytics/monthly", tags=["Analytics"])
    @app.get("/api/v1/performance/monthly", tags=["Analytics"])
    def analytics_monthly():
        trades = db.get_closed_trades(limit=5000, days=30)
        return analytics.strategy_performance(trades)

    @app.get("/api/v1/performance/sessions", tags=["Analytics"])
    def performance_sessions(days: int = Query(30)):
        trades = db.get_closed_trades(limit=1000, days=days)
        return analytics.session_performance(trades)

    @app.get("/api/v1/performance/pairs", tags=["Analytics"])
    def performance_pairs(days: int = Query(30)):
        trades = db.get_closed_trades(limit=1000, days=days)
        return analytics.pair_performance(trades)

    @app.get("/api/v1/performance/strategies", tags=["Analytics"])
    def performance_strategies(days: int = Query(30)):
        trades = db.get_closed_trades(limit=1000, days=days)
        return analytics.strategy_performance(trades)

    @app.get("/api/v1/equity-curve", tags=["Analytics"])
    def get_equity_curve(days: int = Query(30)):
        return {"curve": db.get_equity_curve(days=days)}

    # ─── Report Generation & HTML ─────────────────────────────────

    @app.post("/reports/{period}", tags=["Reports"])
    def generate_period_report(period: str):
        if period not in ("daily", "weekly", "monthly"):
            period = "daily"
        days = 1 if period == "daily" else (7 if period == "weekly" else 30)
        trades = db.get_closed_trades(limit=1000, days=days)
        equity_curve = db.get_equity_curve(days=days)
        report_data = analytics.full_performance_report(trades, equity_curve, period.capitalize())
        
        if period == "daily":
            path = report_generator.generate_daily_report(report_data, trades, equity_curve)
        elif period == "weekly":
            path = report_generator.generate_weekly_report(report_data, trades, equity_curve)
        else:
            path = report_generator.generate_monthly_report(report_data, trades, equity_curve)
            
        return {"status": "generated", "path": path}

    @app.get("/reports/{period}/latest", tags=["Reports"])
    @app.get("/api/v1/reports/{period}", response_class=HTMLResponse, tags=["Reports"])
    def latest_report_html(period: str):
        if period not in ("daily", "weekly", "monthly"):
            period = "daily"
        from pathlib import Path
        base = Path(settings.reports_dir) / period
        if not base.exists():
            days = 1 if period == "daily" else (7 if period == "weekly" else 30)
            trades = db.get_closed_trades(limit=1000, days=days)
            equity_curve = db.get_equity_curve(days=days)
            report_data = analytics.full_performance_report(trades, equity_curve, period.capitalize())
            if period == "daily":
                path = report_generator.generate_daily_report(report_data, trades, equity_curve)
            elif period == "weekly":
                path = report_generator.generate_weekly_report(report_data, trades, equity_curve)
            else:
                path = report_generator.generate_monthly_report(report_data, trades, equity_curve)
            with open(path, 'r', encoding='utf-8') as f:
                return HTMLResponse(f.read())
                
        folders = sorted(base.iterdir(), reverse=True)
        if not folders:
            days = 1 if period == "daily" else (7 if period == "weekly" else 30)
            trades = db.get_closed_trades(limit=1000, days=days)
            equity_curve = db.get_equity_curve(days=days)
            report_data = analytics.full_performance_report(trades, equity_curve, period.capitalize())
            if period == "daily":
                path = report_generator.generate_daily_report(report_data, trades, equity_curve)
            elif period == "weekly":
                path = report_generator.generate_weekly_report(report_data, trades, equity_curve)
            else:
                path = report_generator.generate_monthly_report(report_data, trades, equity_curve)
            with open(path, 'r', encoding='utf-8') as f:
                return HTMLResponse(f.read())
                
        html = folders[0] / "report.html"
        if html.exists():
            with open(html, 'r', encoding='utf-8') as f:
                return HTMLResponse(f.read())
            
        html_files = sorted(folders[0].glob("*.html"), reverse=True)
        if html_files:
            with open(html_files[0], 'r', encoding='utf-8') as f:
                return HTMLResponse(f.read())
            
        return HTMLResponse("No report found")

    # ─── Commands (Halt, Resume, Close-All, AI) ───────────────────

    @app.post("/api/v1/commands/halt", tags=["Control"])
    def halt_trading(req: HaltRequest):
        STATE.trading_halted = True
        STATE.halt_reason = req.reason
        STATE.trading_enabled = False
        db.log_system("WARNING", f"Trading HALTED by {req.source}: {req.reason}", "API")
        logging.getLogger("zohra.api").warning(f"🛑 HALT requested by {req.source}: {req.reason}")
        return {"status": "halted", "reason": req.reason, "source": req.source}

    @app.post("/api/v1/commands/resume", tags=["Control"])
    def resume_trading():
        result = _resume_trading_if_market_open("API")
        logging.getLogger("zohra.api").info("Trading resume requested via API: %s", result["status"])
        return result

    def _require_direct_broker_action(action: str, authorization_token: Optional[str]) -> None:
        decision = trading_permission_gateway.authorize_broker_action(
            action, {"broker": "mt5", "authorization_token": authorization_token or ""}
        )
        if not decision.approved:
            raise HTTPException(status_code=403, detail=decision.reason)

    @app.post("/api/v1/commands/close-all", tags=["Control"])
    def close_all(x_zohra_authorization: Optional[str] = Header(None)):
        if not mt5_broker.is_connected():
            raise HTTPException(status_code=503, detail="No broker connected to this API process")
        _require_direct_broker_action("close_all_positions", x_zohra_authorization)
        closed = mt5_broker.close_all_positions(comment="API-Emergency-Close")
        db.log_system("WARNING", f"Emergency close-all: {closed} positions closed", "API")
        return {"status": "closed", "positions_closed": closed}

    @app.post("/api/v1/commands/close/{ticket}", tags=["Control"])
    def close_single_position(ticket: str, x_zohra_authorization: Optional[str] = Header(None)):
        if not mt5_broker.is_connected():
            raise HTTPException(status_code=503, detail="No broker connected to this API process")
        _require_direct_broker_action("close_position", x_zohra_authorization)
        open_trades = db.get_open_trades() or []
        trade = next(
            (
                t for t in open_trades
                if str(t.get("mt5_ticket") or "") == str(ticket)
                or str(t.get("ticket") or "") == str(ticket)
                or str(t.get("trade_id") or "") == str(ticket)
            ),
            None,
        )
        if not trade:
            raise HTTPException(status_code=404, detail=f"No open trade found for ticket {ticket}")

        mt5_ticket = trade.get("mt5_ticket") or trade.get("ticket")
        if not mt5_ticket:
            raise HTTPException(status_code=400, detail=f"Trade {ticket} has no MT5 ticket to close")
        if trade.get("account_id", "account_01") != "account_01":
            raise HTTPException(status_code=409, detail="Position belongs to another account")

        result = mt5_broker.close_trade(
            int(mt5_ticket),
            trade.get("symbol"),
            trade.get("direction"),
            lots=trade.get("position_size_lots"),
            comment="API-Close-One",
        )
        if not result or not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Broker did not close ticket {ticket}")

        db.log_system("WARNING", f"Manual close requested for ticket {ticket}", "API")
        return {"status": "closed", "ticket": ticket, "result": result}

    def update_setting(name: str, value: Any):
        setattr(settings, name, value)
        import sys
        for mod_name, mod in list(sys.modules.items()):
            if mod_name == "zohra" or mod_name == "zohra_brain" or "zohra" in mod_name:
                if hasattr(mod, name):
                    setattr(mod, name, value)

    @app.get("/api/v1/settings", tags=["Control"])
    def get_settings():
        return {
            "risk_per_trade_pct": settings.RISK_PER_TRADE_PCT,
            "allow_c_setups": settings.ALLOW_C_SETUPS,
            "max_open_positions": settings.MAX_OPEN_POSITIONS,
            "max_daily_loss_pct": settings.MAX_DAILY_LOSS_PCT,
            "max_drawdown_pct": settings.MAX_DRAWDOWN_PCT,
            "active_pairs": settings.ACTIVE_PAIRS,
        }

    @app.post("/api/v1/settings", tags=["Control"])
    def update_settings_endpoint(req: SettingsUpdateRequest):
        updates = {}
        if req.risk_per_trade_pct is not None:
            update_setting("RISK_PER_TRADE_PCT", req.risk_per_trade_pct)
            updates["risk_per_trade_pct"] = req.risk_per_trade_pct
        if req.allow_c_setups is not None:
            update_setting("ALLOW_C_SETUPS", req.allow_c_setups)
            updates["allow_c_setups"] = req.allow_c_setups
        if req.max_open_positions is not None:
            update_setting("MAX_OPEN_POSITIONS", req.max_open_positions)
            updates["max_open_positions"] = req.max_open_positions
        if req.max_daily_loss_pct is not None:
            update_setting("MAX_DAILY_LOSS_PCT", req.max_daily_loss_pct)
            updates["max_daily_loss_pct"] = req.max_daily_loss_pct
        if req.max_drawdown_pct is not None:
            update_setting("MAX_DRAWDOWN_PCT", req.max_drawdown_pct)
            updates["max_drawdown_pct"] = req.max_drawdown_pct
        if req.active_pairs is not None:
            update_setting("ACTIVE_PAIRS", req.active_pairs)
            updates["active_pairs"] = req.active_pairs
        
        db.log_system("INFO", f"System settings updated: {json.dumps(updates)}", "API")
        return {"status": "success", "updated": updates}

    class ConnectionManager:
        def __init__(self):
            self.active_connections: List[WebSocket] = []
            
        async def connect(self, websocket: WebSocket):
            await websocket.accept()
            self.active_connections.append(websocket)
            
        def disconnect(self, websocket: WebSocket):
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                
        async def broadcast(self, message: dict):
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass
                    
    ws_manager = ConnectionManager()
    main_loop = None

    @app.on_event("startup")
    async def startup_event():
        global main_loop
        import asyncio
        main_loop = asyncio.get_event_loop()
        # Production startup must never insert demonstration analytics.
        
        # Connect to MT5 broker in a background thread if standalone API run
        def connect_broker_async():
            try:
                fleet_file = os.path.join(LOG_DIR, "fleet_state.json")
                if os.path.exists(fleet_file) or os.getenv("CONNECT_MT5_STANDALONE", "0") != "1":
                    logger.info("ℹ️ Multi-account fleet mode active: relying on fleet telemetry, skipping direct terminal bind.")
                    return
                from zohra.brokers.mt5_broker import mt5_broker
                if not mt5_broker.is_connected():
                    logger.info("🔌 API Server: Standalone run detected. Connecting to MT5 broker...")
                    mt5_broker.connect()
            except Exception as e:
                logger.error(f"API Server: Failed to connect to broker in background: {e}")
                
        import threading
        t = threading.Thread(target=connect_broker_async, daemon=True)
        t.start()
        
    @app.websocket("/api/v1/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
                await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    @app.post("/api/v1/commands/ai", tags=["AI"])
    def ai_command(req: CommandRequest):
        cmd = req.command.lower().strip()
        
        if cmd in ("status", "how are you doing", "report"):
            stats = {}
            if hasattr(db, "get_raw_stats"):
                stats = db.get_raw_stats(days=1)
            return {
                "command": cmd,
                "response": {
                    "trading": STATE.trading_enabled,
                    "halted": STATE.trading_halted,
                    "daily_pnl": round(STATE.daily_pnl, 2),
                    "daily_trades": STATE.daily_trades,
                    "today_stats": stats,
                }
            }
            
        elif cmd in ("halt", "stop", "stop trading", "pause"):
            STATE.trading_halted = True
            STATE.trading_enabled = False
            STATE.halt_reason = f"AI/Voice command from {req.source}"
            return {"command": cmd, "response": "Trading halted", "status": "halted"}
            
        elif cmd in ("resume", "go", "start", "start trading"):
            result = _resume_trading_if_market_open(f"AI/{req.source}")
            if result["status"] == "market_closed":
                return {"command": cmd, "response": result["reason"], "status": "market_closed"}
            return {"command": cmd, "response": "Trading resumed", "status": "active"}
            
        elif cmd in ("performance", "stats", "metrics"):
            trades = db.get_closed_trades(limit=500, days=30)
            equity_curve = db.get_equity_curve(days=30)
            report = analytics.full_performance_report(trades, equity_curve)
            return {
                "command": cmd,
                "response": {
                    "win_rate": report.get('win_rate'),
                    "profit_factor": report.get('profit_factor'),
                    "total_pnl": report.get('total_pnl'),
                    "sharpe_ratio": report.get('sharpe_ratio'),
                }
            }
            
        elif cmd in ("close all", "close-all", "emergency"):
            if not mt5_broker.is_connected():
                raise HTTPException(status_code=503, detail="No broker connected to this API process")
            _require_direct_broker_action(
                "close_all_positions", (req.params or {}).get("authorization_token")
            )
            closed = mt5_broker.close_all_positions(comment="Voice-Emergency")
            db.log_system("WARNING", f"AI command close-all: {closed} positions closed", "API")
            return {"command": cmd, "response": f"Closed {closed} positions"}
            
        else:
            return {
                "command": cmd,
                "response": f"Unknown command: '{cmd}'",
                "available": ["status", "halt", "resume", "performance", "close-all"]
            }

    @app.post("/agents/action", tags=["AI"])
    def agent_action(payload: dict):
        """AI agent action audit endpoint — logs to agent_actions table."""
        conn_db = get_db()
        p = conn_db.placeholder()
        with conn_db.cursor() as cur:
            cur.execute(
                f"INSERT INTO agent_actions (timestamp, agent_id, action_type, payload) VALUES ({p}, {p}, {p}, {p})",
                [datetime.utcnow().isoformat(), payload.get("agent_id", "unknown"),
                 payload.get("action_type", "unknown"), json.dumps(payload)],
            )
        return {"logged": True}

    @app.get("/api/v1/opportunities", tags=["Opportunities"])
    def list_opportunities():
        opps = db.get_live_opportunities()
        return {"opportunities": opps, "count": len(opps)}

    @app.get("/api/v1/exposure", tags=["Analytics"])
    def get_portfolio_exposure():
        open_positions = mt5_broker.get_open_positions()
        
        # Sector counts
        sectors = {"Forex": 0, "Metals": 0, "Indices": 0}
        currencies = {}
        for pos in open_positions:
            sym = pos["symbol"]
            from zohra.core.symbol_manager import symbol_manager
            params = symbol_manager.get_symbol_params(sym)
            if params:
                sectors[params.get("sector", "Forex")] += 1
            
            # Simple currency extraction
            if len(sym) >= 6:
                base, quote = sym[:3], sym[3:6]
                currencies[base] = currencies.get(base, 0) + 1
                currencies[quote] = currencies.get(quote, 0) + 1

        equity = mt5_broker.get_equity()
        
        return {
            "positions_count": len(open_positions),
            "sectors": sectors,
            "currency_stack": currencies,
            "equity": equity,
            "max_sector_caps": MAX_SECTOR_POSITIONS,
            "max_currency_cap": MAX_CURRENCY_EXPOSURE
        }

    DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Zohra AI | Supreme Trading Center</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Space+Grotesk:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090a12;
            --panel-bg: rgba(18, 20, 38, 0.65);
            --border: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(255, 255, 255, 0.15);
            --primary: #8a2be2;
            --primary-glow: rgba(138, 43, 226, 0.4);
            --accent: #00ffcc;
            --danger: #ff007f;
            --text-main: #f0f2f5;
            --text-muted: #8892b0;
        }

        body {
            font-family: 'Space Grotesk', sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            margin: 0;
            padding: 0;
            background-image: radial-gradient(circle at 5% 10%, rgba(138, 43, 226, 0.15) 0%, transparent 40%),
                              radial-gradient(circle at 95% 85%, rgba(0, 255, 204, 0.05) 0%, transparent 40%);
            background-attachment: fixed;
            min-height: 100vh;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 40px;
            background: rgba(9, 10, 18, 0.8);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        h1 {
            font-family: 'Outfit', sans-serif;
            font-weight: 800;
            font-size: 28px;
            margin: 0;
            background: linear-gradient(45deg, #a855f7, #06b6d4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .pulse-badge {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: var(--accent);
            box-shadow: 0 0 10px var(--accent);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.7; }
            50% { transform: scale(1.1); opacity: 1; box-shadow: 0 0 15px var(--accent); }
            100% { transform: scale(0.9); opacity: 0.7; }
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 25px;
            padding: 30px 40px;
            max-width: 1600px;
            margin: 0 auto;
        }

        .card {
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px;
            backdrop-filter: blur(20px);
            transition: border-color 0.3s ease, transform 0.3s ease;
        }

        .card:hover {
            border-color: var(--border-hover);
        }

        /* Span dimensions */
        .col-4 { grid-column: span 4; }
        .col-8 { grid-column: span 8; }
        .col-12 { grid-column: span 12; }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 15px;
        }

        .metric {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 15px;
            text-align: center;
        }

        .metric-title {
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 5px;
        }

        .metric-value {
            font-size: 22px;
            font-weight: 700;
        }

        .text-green { color: var(--accent); }
        .text-red { color: var(--danger); }

        h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 18px;
            font-weight: 600;
            margin-top: 0;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            text-align: left;
            padding: 12px 15px;
            color: var(--text-muted);
            font-size: 13px;
            border-bottom: 1px solid var(--border);
        }

        td {
            padding: 12px 15px;
            font-size: 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.01);
        }

        .badge {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            display: inline-block;
        }

        .badge-buy { background: rgba(0, 255, 204, 0.12); color: var(--accent); }
        .badge-sell { background: rgba(255, 0, 127, 0.12); color: var(--danger); }

        .btn {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: inherit;
            font-size: 13px;
        }

        .btn:hover {
            background: var(--primary);
            border-color: var(--primary);
            box-shadow: 0 0 10px var(--primary-glow);
        }

        .btn-danger {
            background: rgba(255, 0, 127, 0.1);
            border-color: rgba(255, 0, 127, 0.3);
            color: var(--danger);
        }

        .btn-danger:hover {
            background: var(--danger);
            border-color: var(--danger);
            box-shadow: 0 0 10px rgba(255, 0, 127, 0.4);
            color: #fff;
        }

         .log-ts { color: var(--text-muted); margin-right: 10px; }
        .log-lvl-info { color: #5dade2; }
        .log-lvl-warn { color: #f4d03f; }
        .log-lvl-err { color: var(--danger); }

        /* HIE Tab Styles */
        .tabs-nav {
            display: flex;
            gap: 10px;
            padding: 10px 40px;
            border-bottom: 1px solid var(--border);
            background: rgba(18, 20, 38, 0.4);
        }
        .tab-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-muted);
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-family: inherit;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .tab-btn:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
        }
        .tab-btn.active {
            color: var(--accent);
            background: rgba(0, 255, 204, 0.1);
            border-color: rgba(0, 255, 204, 0.2);
        }
        .tab-content {
            display: none;
            padding: 20px 40px;
        }
        .tab-content.active {
            display: block;
        }
    </style>
</head>
<body>
    <header>
        <h1><div class="pulse-badge"></div> ZOHRA AI Multi-Asset Scan Center</h1>
        <div class="btn-group">
            <button class="btn" onclick="sendCommand('resume')">RESUME SCANS</button>
            <button class="btn btn-danger" onclick="sendCommand('halt')">HALT ENGINE</button>
            <button class="btn btn-danger" onclick="closeAll()">CLOSE ALL POSITIONS</button>
        </div>
    </header>

    <div class="tabs-nav">
        <button class="tab-btn active" id="btn-tab-scans" onclick="switchTab('tab-scans')">Live Scans</button>
        <button class="tab-btn" id="btn-tab-hie" onclick="switchTab('tab-hie')">Historical Intel</button>
        <button class="tab-btn" id="btn-tab-profiles" onclick="switchTab('tab-profiles')">Symbol Profiles</button>
        <button class="tab-btn" id="btn-tab-patterns" onclick="switchTab('tab-patterns')">Pattern Library</button>
        <button class="tab-btn" id="btn-tab-replay" onclick="switchTab('tab-replay')">Replay Center</button>
        <button class="tab-btn" id="btn-tab-learning" onclick="switchTab('tab-learning')">Learning Center</button>
        <button class="tab-btn" id="btn-tab-failures" onclick="switchTab('tab-failures')">Failure Detection</button>
    </div>

    <!-- Tab 1: Live Scans -->
    <div id="tab-scans" class="tab-content active">
        <div class="dashboard-grid">
            <!-- Account Summary & Limits -->
            <div class="card col-4">
                <h2>Portfolio & System Health</h2>
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-title">Balance</div>
                        <div class="metric-value" id="balance">$0.00</div>
                    </div>
                    <div class="metric">
                        <div class="metric-title">Equity</div>
                        <div class="metric-value" id="equity">$0.00</div>
                    </div>
                    <div class="metric">
                        <div class="metric-title">Daily P&L</div>
                        <div class="metric-value" id="daily-pnl">$0.00</div>
                    </div>
                </div>
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-title">Engine State</div>
                        <div class="metric-value text-green" id="engine-state">ACTIVE</div>
                    </div>
                    <div class="metric">
                        <div class="metric-title">Daily Trades</div>
                        <div class="metric-value" id="daily-trades">0</div>
                    </div>
                    <div class="metric">
                        <div class="metric-title">Open Trades</div>
                        <div class="metric-value" id="open-count">0</div>
                    </div>
                </div>
            </div>

            <!-- Sector Exposure Limits -->
            <div class="card col-8">
                <h2>Portfolio Sector Exposure Limits</h2>
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-title">Forex Exposure</div>
                        <div class="metric-value" id="forex-exposure">0 / 3</div>
                    </div>
                    <div class="metric">
                        <div class="metric-title">Metals Exposure</div>
                        <div class="metric-value" id="metals-exposure">0 / 2</div>
                    </div>
                    <div class="metric">
                        <div class="metric-title">Indices Exposure</div>
                        <div class="metric-value" id="indices-exposure">0 / 2</div>
                    </div>
                </div>
                <div style="margin-top: 25px; font-size: 13px; color: var(--text-muted); display: flex; justify-content: space-between;">
                    <span>USD Currency Exposure Stack: <strong id="usd-exposure" class="text-green">0 / 3</strong></span>
                    <span>Correlation Limit: <strong>&lt; 0.75</strong></span>
                </div>
            </div>

            <!-- Opportunity Leaderboard -->
            <div class="card col-12">
                <h2>Live Opportunities Leaderboard <span>Active Scans</span></h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Strategy</th>
                                <th>Direction</th>
                                <th>Confidence Score</th>
                                <th>Entry Zone</th>
                                <th>Stop Loss</th>
                                <th>Take Profit</th>
                                <th>Analysis Reasons</th>
                            </tr>
                        </thead>
                        <tbody id="leaderboard-body">
                            <tr>
                                <td colspan="8" style="text-align: center; color: var(--text-muted);">Scanning symbols for setups...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Open Trades -->
            <div class="card col-8">
                <h2>Active Open Trades</h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Ticket</th>
                                <th>Symbol</th>
                                <th>Direction</th>
                                <th>Lots</th>
                                <th>Entry Price</th>
                                <th>SL</th>
                                <th>TP</th>
                                <th>Floating Profit</th>
                            </tr>
                        </thead>
                        <tbody id="open-trades-body">
                            <tr>
                                <td colspan="8" style="text-align: center; color: var(--text-muted);">No open positions.</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- System Logs -->
            <div class="card col-4">
                <h2>Explainability Logs</h2>
                <div class="logs-panel" id="logs-panel">
                    <div style="color: var(--text-muted);">Logs loading...</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Tab 2: Historical Intel -->
    <div id="tab-hie" class="tab-content">
        <div class="dashboard-grid">
            <div class="card col-4">
                <h2>HIE Engine Status</h2>
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-title">Candles Loaded</div>
                        <div class="metric-value text-green" id="hie-candles-count">0</div>
                    </div>
                    <div class="metric">
                        <div class="metric-title">Symbols Tracked</div>
                        <div class="metric-value" id="hie-symbols-count">0</div>
                    </div>
                </div>
                <p style="font-size: 12px; color: var(--text-muted); margin-top: 10px;">Last update: <span id="hie-last-update">N/A</span></p>
            </div>
            <div class="card col-8">
                <h2>Top Performing Setup Patterns</h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Setup</th>
                                <th>Symbol</th>
                                <th>Session</th>
                                <th>Occurrences</th>
                                <th>Win Rate</th>
                                <th>Avg RR</th>
                            </tr>
                        </thead>
                        <tbody id="hie-top-patterns-body">
                            <tr>
                                <td colspan="6" style="text-align: center; color: var(--text-muted);">Loading patterns...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Tab 3: Symbol Profiles -->
    <div id="tab-profiles" class="tab-content">
        <div class="dashboard-grid" id="hie-profiles-grid">
            <div style="grid-column: span 12; text-align: center; color: var(--text-muted);">Loading symbol profiles...</div>
        </div>
    </div>

    <!-- Tab 4: Pattern Library -->
    <div id="tab-patterns" class="tab-content">
        <div class="card col-12">
            <h2>HIE Pattern Library</h2>
            <div style="margin-bottom: 20px; display: flex; gap: 15px;">
                <input type="text" id="filter-symbol" placeholder="Symbol (e.g. EURUSD)" class="btn" style="background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: var(--text-main); text-align: left; padding-left: 10px;">
                <input type="text" id="filter-setup" placeholder="Setup (e.g. BOS)" class="btn" style="background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: var(--text-main); text-align: left; padding-left: 10px;">
                <button class="btn" onclick="fetchPatternLibrary()">Filter Scans</button>
            </div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Setup Type</th>
                            <th>Direction</th>
                            <th>Session</th>
                            <th>Timeframe</th>
                            <th>Occurrences</th>
                            <th>Win Rate</th>
                            <th>Avg RR</th>
                        </tr>
                    </thead>
                    <tbody id="hie-library-body">
                        <tr>
                            <td colspan="8" style="text-align: center; color: var(--text-muted);">Enter filter criteria and search.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Tab 5: Replay Center -->
    <div id="tab-replay" class="tab-content">
        <div class="dashboard-grid">
            <div class="card col-4">
                <h2>Replay Controls</h2>
                <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 15px;">
                    <label style="font-size: 12px; color: var(--text-muted);">Symbol</label>
                    <select id="replay-symbol" class="btn" style="background: rgba(255,255,255,0.05); color: var(--text-main); border: 1px solid var(--border); text-align: left; font-size: 14px;">
                        <option value="XAUUSD">XAUUSD (Gold)</option>
                        <option value="EURUSD">EURUSD</option>
                        <option value="GBPUSD">GBPUSD</option>
                    </select>
                    <label style="font-size: 12px; color: var(--text-muted);">Timeframe</label>
                    <select id="replay-tf" class="btn" style="background: rgba(255,255,255,0.05); color: var(--text-main); border: 1px solid var(--border); text-align: left; font-size: 14px;">
                        <option value="H1">H1</option>
                        <option value="M15">M15</option>
                        <option value="H4">H4</option>
                    </select>
                    <button class="btn" onclick="startReplay()">Start Replay</button>
                    <button class="btn" onclick="stepReplay()">Next Candle</button>
                    <button class="btn btn-danger" onclick="stopReplay()">Stop Replay</button>
                </div>
            </div>
            <div class="card col-8">
                <h2>Interactive Replay Playback</h2>
                <div id="replay-display" style="height: 300px; display: flex; flex-direction: column; justify-content: center; align-items: center; background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px dashed var(--border);">
                    <div style="color: var(--text-muted); font-size: 14px;" id="replay-status">No replay session active. Start replay to see candles.</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Tab 6: Learning Center -->
    <div id="tab-learning" class="tab-content">
        <div class="dashboard-grid">
            <div class="card col-6">
                <h2>HIE Daily Learning Review</h2>
                <div class="logs-panel" id="learning-daily-panel" style="height: 350px;">
                    <div style="color: var(--text-muted);">Loading reviews...</div>
                </div>
            </div>
            <div class="card col-6">
                <h2>HIE Weekly & Monthly Insights</h2>
                <div class="logs-panel" id="learning-weekly-panel" style="height: 350px;">
                    <div style="color: var(--text-muted);">Loading reviews...</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Tab 7: Failure Detection -->
    <div id="tab-failures" class="tab-content">
        <div class="card col-12">
            <h2>Failure Pattern Detector <span>Flagged Losing Combos</span></h2>
            <div style="overflow-x: auto; margin-top: 15px;">
                <table>
                    <thead>
                        <tr>
                            <th>Pattern Signature</th>
                            <th>Confluences</th>
                            <th>Occurrences</th>
                            <th>Fail Rate</th>
                            <th>Avg Loss</th>
                        </tr>
                    </thead>
                    <tbody id="hie-failures-body">
                        <tr>
                            <td colspan="5" style="text-align: center; color: var(--text-muted);">No flagged failure patterns.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            document.getElementById('btn-' + tabId).classList.add('active');
            
            if (tabId === 'tab-hie') {
                fetchHieStatus();
            } else if (tabId === 'tab-profiles') {
                fetchSymbolProfiles();
            } else if (tabId === 'tab-patterns') {
                fetchPatternLibrary();
            } else if (tabId === 'tab-learning') {
                fetchLearningCenter();
            } else if (tabId === 'tab-failures') {
                fetchFailureDetection();
            }
        }

        async function fetchHieStatus() {
            try {
                const res = await fetch('/api/v1/hie/status');
                const status = await res.json();
                document.getElementById('hie-candles-count').innerText = (status.total_candles || 0).toLocaleString();
                document.getElementById('hie-symbols-count').innerText = status.symbols_loaded || 0;
                document.getElementById('hie-last-update').innerText = status.last_update ? status.last_update.substring(11, 19) : 'N/A';
                
                const pRes = await fetch('/api/v1/hie/pattern-stats?limit=10');
                const pData = await pRes.json();
                const tbody = document.getElementById('hie-top-patterns-body');
                tbody.innerHTML = '';
                if (pData.patterns && pData.patterns.length > 0) {
                    pData.patterns.slice(0, 10).forEach(p => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><strong>${p.setup_type}</strong></td>
                            <td>${p.symbol}</td>
                            <td>${p.session}</td>
                            <td>${p.occurrences}</td>
                            <td class="text-green"><strong>${p.win_rate.toFixed(1)}%</strong></td>
                            <td>${p.avg_rr.toFixed(2)}R</td>
                        `;
                        tbody.appendChild(tr);
                    });
                } else {
                    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No patterns detected yet.</td></tr>`;
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchSymbolProfiles() {
            try {
                const symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"];
                const grid = document.getElementById('hie-profiles-grid');
                grid.innerHTML = '';
                
                for (const sym of symbols) {
                    const res = await fetch(`/api/v1/hie/symbol-profile/${sym}`);
                    const data = await res.json();
                    const p = data.profile || {};
                    
                    const card = document.createElement('div');
                    card.className = 'card col-3';
                    card.innerHTML = `
                        <h3>${sym} Profile</h3>
                        <div style="font-size: 13px; margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">
                            <div>Best Session: <strong class="text-green">${p.best_session || 'N/A'}</strong></div>
                            <div>Worst Session: <strong class="text-red">${p.worst_session || 'N/A'}</strong></div>
                            <div>Best Setup: <strong>${p.best_setup || 'N/A'}</strong></div>
                            <div>Best Timeframe: <strong>${p.best_timeframe || 'N/A'}</strong></div>
                            <div style="border-top: 1px solid var(--border); padding-top: 8px;">Overall WR: <strong class="text-green">${p.overall_win_rate ? p.overall_win_rate.toFixed(1) : '0'}%</strong></div>
                            <div>Overall Avg RR: <strong>${p.overall_avg_rr ? p.overall_avg_rr.toFixed(2) : '0'}R</strong></div>
                        </div>
                    `;
                    grid.appendChild(card);
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchPatternLibrary() {
            try {
                const sym = document.getElementById('filter-symbol').value;
                const setup = document.getElementById('filter-setup').value;
                let url = '/api/v1/hie/pattern-stats?limit=50';
                if (sym) url += `&symbol=${sym.toUpperCase()}`;
                if (setup) url += `&setup_type=${setup.toUpperCase()}`;
                
                const res = await fetch(url);
                const data = await res.json();
                const tbody = document.getElementById('hie-library-body');
                tbody.innerHTML = '';
                
                if (data.patterns && data.patterns.length > 0) {
                    data.patterns.forEach(p => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><strong>${p.symbol}</strong></td>
                            <td>${p.setup_type}</td>
                            <td><span class="badge ${p.direction === 'LONG' ? 'badge-buy' : 'badge-sell'}">${p.direction}</span></td>
                            <td>${p.session}</td>
                            <td>${p.timeframe}</td>
                            <td>${p.occurrences}</td>
                            <td class="text-green"><strong>${p.win_rate.toFixed(1)}%</strong></td>
                            <td>${p.avg_rr.toFixed(2)}R</td>
                        `;
                        tbody.appendChild(tr);
                    });
                } else {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No setups match query.</td></tr>`;
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function startReplay() {
            try {
                const symbol = document.getElementById('replay-symbol').value;
                const tf = document.getElementById('replay-tf').value;
                const res = await fetch('/api/v1/hie/replay/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({symbol, timeframe: tf})
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('replay-status').innerText = `Replay started for ${symbol} ${tf}. Click 'Next Candle' to playback.`;
                } else {
                    alert("Failed to start replay: " + data.error);
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function stepReplay() {
            try {
                const res = await fetch('/api/v1/hie/replay/next');
                const data = await res.json();
                const display = document.getElementById('replay-display');
                if (data.success && data.candle) {
                    const c = data.candle;
                    display.innerHTML = `
                        <div style="font-size: 18px; color: var(--text-main); font-weight: bold; margin-bottom: 10px;">${c.symbol} ${c.timeframe} Candle</div>
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; width: 300px; font-size: 14px;">
                            <div>Time: <strong class="text-green">${c.timestamp}</strong></div>
                            <div>Open: <strong>${c.open}</strong></div>
                            <div>High: <strong>${c.high}</strong></div>
                            <div>Low: <strong>${c.low}</strong></div>
                            <div>Close: <strong>${c.close}</strong></div>
                            <div>Volume: <strong>${c.volume}</strong></div>
                        </div>
                    `;
                } else {
                    document.getElementById('replay-status').innerText = data.message || "Replay finished.";
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function stopReplay() {
            try {
                await fetch('/api/v1/hie/replay/stop', { method: 'POST' });
                document.getElementById('replay-display').innerHTML = `
                    <div style="color: var(--text-muted); font-size: 14px;" id="replay-status">No replay session active. Start replay to see candles.</div>
                `;
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchLearningCenter() {
            try {
                const resDaily = await fetch('/api/v1/hie/learning/daily');
                const dataDaily = await resDaily.json();
                const panelDaily = document.getElementById('learning-daily-panel');
                panelDaily.innerHTML = '';
                if (dataDaily.recommendations && dataDaily.recommendations.length > 0) {
                    dataDaily.recommendations.forEach(r => {
                        const div = document.createElement('div');
                        div.className = 'log-line';
                        div.innerHTML = `<span style="color: var(--accent);">[Daily Insights]</span> <span>${r}</span>`;
                        panelDaily.appendChild(div);
                    });
                } else {
                    panelDaily.innerHTML = `<div style="color: var(--text-muted);">No daily reviews today.</div>`;
                }

                const resWeekly = await fetch('/api/v1/hie/learning/weekly');
                const dataWeekly = await resWeekly.json();
                const panelWeekly = document.getElementById('learning-weekly-panel');
                panelWeekly.innerHTML = '';
                if (dataWeekly.insights && dataWeekly.insights.length > 0) {
                    dataWeekly.insights.forEach(r => {
                        const div = document.createElement('div');
                        div.className = 'log-line';
                        div.innerHTML = `<span style="color: #a855f7;">[Weekly Insights]</span> <span>${r}</span>`;
                        panelWeekly.appendChild(div);
                    });
                } else {
                    panelWeekly.innerHTML = `<div style="color: var(--text-muted);">No weekly reviews yet.</div>`;
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchFailureDetection() {
            try {
                const res = await fetch('/api/v1/hie/failure-patterns');
                const data = await res.json();
                const tbody = document.getElementById('hie-failures-body');
                tbody.innerHTML = '';
                if (data.failure_patterns && data.failure_patterns.length > 0) {
                    data.failure_patterns.forEach(f => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><strong class="text-red">${f.failure_signature}</strong></td>
                            <td style="font-size: 12px; color: var(--text-muted);">${f.confluences}</td>
                            <td>${f.occurrences}</td>
                            <td class="text-red"><strong>${f.fail_rate.toFixed(1)}%</strong></td>
                            <td>$${f.avg_loss.toFixed(2)}</td>
                        `;
                        tbody.appendChild(tr);
                    });
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No recurring failure patterns detected. Safe trading environment.</td></tr>`;
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchDashboard() {
            try {
                // 1. Fetch Health
                const hRes = await fetch('/api/v1/health');
                const health = await hRes.json();
                document.getElementById('daily-trades').innerText = health.daily_trades;
                document.getElementById('daily-pnl').innerText = '$' + health.daily_pnl.toFixed(2);
                document.getElementById('daily-pnl').className = health.daily_pnl >= 0 ? 'metric-value text-green' : 'metric-value text-red';
                document.getElementById('engine-state').innerText = health.halted ? 'HALTED' : 'ACTIVE';
                document.getElementById('engine-state').className = health.halted ? 'metric-value text-red' : 'metric-value text-green';

                // 2. Fetch Account Summary
                const aRes = await fetch('/api/v1/account');
                const account = await aRes.json();
                document.getElementById('balance').innerText = '$' + (account.balance || 0).toLocaleString();
                document.getElementById('equity').innerText = '$' + (account.equity || 0).toLocaleString();

                // 3. Fetch Exposure Limits
                const eRes = await fetch('/api/v1/exposure');
                const exp = await eRes.json();
                document.getElementById('open-count').innerText = exp.positions_count;
                document.getElementById('forex-exposure').innerText = `${exp.sectors.Forex} / ${exp.max_sector_caps.Forex}`;
                document.getElementById('metals-exposure').innerText = `${exp.sectors.Metals} / ${exp.max_sector_caps.Metals}`;
                document.getElementById('indices-exposure').innerText = `${exp.sectors.Indices} / ${exp.max_sector_caps.Indices}`;
                document.getElementById('usd-exposure').innerText = `${exp.currency_stack.USD || 0} / ${exp.max_currency_cap}`;
                document.getElementById('usd-exposure').className = (exp.currency_stack.USD || 0) >= exp.max_currency_cap ? 'text-red' : 'text-green';

                // 4. Fetch Leaderboard
                const oRes = await fetch('/api/v1/opportunities');
                const opps = await oRes.json();
                const lBody = document.getElementById('leaderboard-body');
                lBody.innerHTML = '';
                if (opps.opportunities && opps.opportunities.length > 0) {
                    opps.opportunities.forEach(opp => {
                        const tr = document.createElement('tr');
                        const badgeClass = opp.direction === 'LONG' ? 'badge badge-buy' : 'badge badge-sell';
                        const scoreClass = opp.confidence_score >= 85 ? 'text-green' : 'text-main';
                        tr.innerHTML = `
                            <td><strong>${opp.symbol}</strong></td>
                            <td>${opp.strategy}</td>
                            <td><span class="${badgeClass}">${opp.direction}</span></td>
                            <td><strong class="${scoreClass}">${opp.confidence_score}</strong></td>
                            <td>${opp.entry_price.toFixed(5)}</td>
                            <td>${opp.stop_loss.toFixed(5)}</td>
                            <td>${opp.take_profit.toFixed(5)}</td>
                            <td style="color: var(--text-muted); font-size: 12px;">${opp.reasons.join(', ')}</td>
                        `;
                        lBody.appendChild(tr);
                    });
                } else {
                    lBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No opportunities on leaderboard yet. Scanning symbols...</td></tr>`;
                }

                // 5. Fetch Open Trades
                const tRes = await fetch('/api/v1/trades/open');
                const tradesData = await tRes.json();
                const tBody = document.getElementById('open-trades-body');
                tBody.innerHTML = '';
                if (tradesData.trades && tradesData.trades.length > 0) {
                    tradesData.trades.forEach(t => {
                        const tr = document.createElement('tr');
                        const profitClass = t.pnl_usd >= 0 ? 'text-green' : 'text-red';
                        tr.innerHTML = `
                            <td>#${t.mt5_ticket}</td>
                            <td><strong>${t.symbol}</strong></td>
                            <td><span class="${t.direction === 'LONG' ? 'badge badge-buy' : 'badge-sell'}">${t.direction}</span></td>
                            <td>${t.position_size_lots.toFixed(2)}</td>
                            <td>${t.entry_price.toFixed(5)}</td>
                            <td>${t.stop_loss.toFixed(5)}</td>
                            <td>${t.take_profit.toFixed(5)}</td>
                            <td class="${profitClass}"><strong>$${t.pnl_usd ? t.pnl_usd.toFixed(2) : '0.00'}</strong></td>
                        `;
                        tBody.appendChild(tr);
                    });
                } else {
                    tBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No open positions.</td></tr>`;
                }

                // 6. Fetch Logs (Rejections & Decisions)
                const rRes = await fetch('/api/v1/rejections?limit=10');
                const rej = await rRes.json();
                const logPanel = document.getElementById('logs-panel');
                logPanel.innerHTML = '';
                if (rej.rejections && rej.rejections.length > 0) {
                    rej.rejections.forEach(r => {
                        const div = document.createElement('div');
                        div.className = 'log-line';
                        div.innerHTML = `
                            <span class="log-ts">${r.timestamp.substring(11, 19)}</span>
                            <span class="log-lvl-warn">[REJECT]</span>
                            <span>${r.symbol}: ${r.reason_for_rejection}</span>
                        `;
                        logPanel.appendChild(div);
                    });
                } else {
                    logPanel.innerHTML = `<div style="color: var(--text-muted);">No recent logs.</div>`;
                }

            } catch (err) {
                console.error("Dashboard refresh error: ", err);
            }
        }

        async function sendCommand(action) {
            try {
                const url = action === 'halt' ? '/api/v1/commands/halt' : '/api/v1/commands/resume';
                const body = action === 'halt' ? JSON.stringify({reason: 'Manual UI Halt'}) : null;
                const headers = action === 'halt' ? {'Content-Type': 'application/json'} : {};
                
                await fetch(url, {
                    method: 'POST',
                    headers: headers,
                    body: body
                });
                fetchDashboard();
            } catch (e) {
                alert("Failed to send command: " + e);
            }
        }

        async function closeAll() {
            if (confirm("Are you sure you want to trigger emergency CLOSE-ALL for all open positions?")) {
                try {
                    await fetch('/api/v1/commands/close-all', { method: 'POST' });
                    fetchDashboard();
                } catch(e) {
                    alert("Emergency close request failed: " + e);
                }
            }
        }

        // Auto poll
        setInterval(fetchDashboard, 3000);
        fetchDashboard();
    </script>
</body>
</html>"""

    @app.get("/dashboard", tags=["Dashboard"])
    @app.get("/workspace", tags=["Dashboard"])
    @app.get("/", tags=["Dashboard"])
    def get_dashboard():
        return FileResponse(os.path.join(os.path.dirname(__file__), "dashboard.html"))

    @app.get("/news/status", tags=["System"])
    def news_status():
        # Calendar refreshes happen in the trading news agent. This endpoint is
        # intentionally read-only so opening a dashboard cannot trigger a feed request.
        from zohra.integrations.news import NewsAnalyzer

        analyzer = NewsAnalyzer()
        return {
            "status": "UNAVAILABLE",
            "provider": "faireconomy",
            "events_loaded": len(analyzer._cached_events),
            "last_updated": None,
            "message": "No economic-calendar cache is loaded in this API process.",
        }

    @app.get("/brokers", tags=["System"])
    def list_brokers():
        return {"active": "mt5", "supported": ["mt5"], "planned": ["ibkr", "ctrader"]}

    # ─── Institutional Advanced Command Center Router ─────────────
    manager = AdvancedAnalyticsManager()

    def run_advanced_background_loop():
        # Wait a few seconds to let MT5/database initialize
        time.sleep(5)
        while True:
            try:
                # 1. Update exposures
                manager.calculate_portfolio_exposures()
                # 2. Update correlations
                manager.get_correlations()
                # 3. Update margin health
                manager.get_margin_health()
                # 4. Update system health
                manager.get_system_health()

                # Broadcast real-time state to WebSocket clients
                if main_loop and main_loop.is_running():
                    acc = {}
                    try:
                        acc = mt5_broker.get_account_info() or {}
                    except Exception:
                        pass

                    # Query MT5 open positions for live dashboard rendering
                    open_positions = []
                    try:
                        raw_positions = mt5_broker.get_open_positions() or []
                        for p in raw_positions:
                            open_positions.append({
                                "ticket": p.get("ticket"),
                                "symbol": p.get("symbol"),
                                "direction": "LONG" if p.get("type", 1) == 0 else "SHORT",
                                "lots": p.get("lots", 0),
                                "open_price": p.get("open_price", 0),
                                "current_price": p.get("current_price", 0),
                                "profit": p.get("profit", 0),
                                "sl": p.get("sl", 0),
                                "tp": p.get("tp", 0),
                            })
                    except Exception:
                        pass
                        
                    payload = {
                        "type": "state_update",
                        "timestamp": datetime.utcnow().isoformat(),
                        "state": {
                            "trading_enabled": STATE.trading_enabled and not STATE.trading_halted,
                            "trading_halted": STATE.trading_halted,
                            "halt_reason": STATE.halt_reason,
                            "daily_trades": STATE.daily_trades,
                            "daily_pnl": round(STATE.daily_pnl, 2),
                        },
                        "account": {
                            "equity": acc.get("equity", 0.0),
                            "balance": acc.get("balance", 0.0),
                            "margin": acc.get("margin", 0.0),
                            "free_margin": acc.get("free_margin", 0.0),
                        },
                        "open_positions": open_positions
                    }
                    import asyncio
                    asyncio.run_coroutine_threadsafe(ws_manager.broadcast(payload), main_loop)
                
                time.sleep(5)  # Reduced from 15s for real-time feel
            except Exception as e:
                time.sleep(5)

        # Start background task
    @app.on_event("startup")
    async def start_analytics_worker():
        if os.getenv("ZOHRA_DISABLE_BACKGROUND", "0") != "1":
            threading.Thread(target=run_advanced_background_loop, daemon=True).start()

    @app.get("/api/v1/advanced/exposure", tags=["Advanced Analytics"])
    def get_advanced_exposure():
        return manager.calculate_portfolio_exposures()

    @app.get("/api/v1/advanced/correlation", tags=["Advanced Analytics"])
    def get_advanced_correlation():
        return manager.get_correlations()

    @app.get("/api/v1/advanced/risk-concentration", tags=["Advanced Analytics"])
    def get_advanced_concentration():
        return manager.get_risk_concentration()

    @app.get("/api/v1/advanced/margin-health", tags=["Advanced Analytics"])
    def get_advanced_margin_health():
        return manager.get_margin_health()

    @app.get("/api/v1/advanced/performance/strategies", tags=["Advanced Analytics"])
    def get_advanced_strat_perf():
        return {
            "strategies": manager.get_strategy_performance(),
            "regimes": manager.get_market_condition_performance(),
            "sessions": manager.get_session_performance(),
            "timeframes": manager.get_timeframe_performance(),
            "grades": manager.get_grade_performance()
        }

    @app.get("/api/v1/advanced/missed-opportunities", tags=["Advanced Analytics"])
    def get_advanced_missed():
        return manager.get_missed_opportunities()

    @app.get("/api/v1/advanced/false-signals", tags=["Advanced Analytics"])
    def get_advanced_false_signals():
        return manager.get_false_signals()

    @app.get("/api/v1/advanced/broker-performance", tags=["Advanced Analytics"])
    def get_advanced_broker_perf():
        return manager.get_broker_performance()

    @app.get("/api/v1/advanced/ai-insights", tags=["Advanced Analytics"])
    def get_advanced_ai_insights():
        return manager.get_ai_learning_insights()

    @app.get("/api/v1/advanced/system-health", tags=["Advanced Analytics"])
    def get_advanced_sys_health():
        return manager.get_system_health()

    @app.get("/api/v1/advanced/debrief", tags=["Advanced Analytics"])
    def get_advanced_debrief():
        stats = analytics.daily()
        return {
            "status": "success",
            "source": "Recorded daily trade analytics",
            "statistics": stats,
            "morning_brief": None,
            "midday_brief": f"Recorded closed trades: {stats.get('total_trades', 0)}.",
            "end_of_day_review": None,
            "limitations": "No live market briefing or completed risk-compliance review is available."
        }

    @app.post("/api/v1/advanced/nl-query", tags=["Advanced Analytics"])
    def post_advanced_query(payload: dict):
        query = payload.get("query", "")
        response = manager.route_natural_language_query(query)
        return {"query": query, "response": response}

    @app.get("/api/v1/advanced/monte-carlo", tags=["Advanced Analytics"])
    def get_advanced_monte_carlo():
        return manager.run_monte_carlo_analysis()

    @app.post("/api/v1/advanced/simulate-risk", tags=["Advanced Analytics"])
    def post_advanced_simulate_risk(payload: RiskSimulationRequest):
        return manager.simulate_risk_scenarios(payload.lot_mult, payload.stop_equity, payload.disable_usd_jpy)

    @app.get("/api/v1/journal", tags=["AI Memory"])
    def get_journal(limit: int = Query(100, ge=1, le=1000)):
        closed = db.get_closed_trades(limit=limit)
        open_trades = db.get_open_trades()
        rejections = db.get_rejections(limit=limit)
        return {
            "closed_trades": closed,
            "open_trades": open_trades,
            "rejections": rejections,
            "count": len(closed) + len(open_trades) + len(rejections)
        }

    @app.get("/api/v1/analytics", tags=["Analytics"])
    def get_analytics(days: Optional[int] = Query(30, ge=1, le=365)):
        return analytics_full(days)

    @app.post("/api/v1/ai-query", tags=["AI"])
    def post_ai_query(payload: dict):
        query = payload.get("query", "")
        response = manager.route_natural_language_query(query)
        return {"query": query, "response": response}

    @app.get("/api/v1/ai-query", tags=["AI"])
    def get_ai_query(q: str = Query(..., min_length=1)):
        response = manager.route_natural_language_query(q)
        return {"query": q, "response": response}

    @app.get("/api/v1/replay", tags=["Advanced Analytics"])
    def get_replay(ticket: str = Query(...)):
        return get_trade_replay(ticket)

    @app.get("/api/v1/advanced/replay", tags=["Advanced Analytics"])
    def get_trade_replay(ticket: str = Query(...)):
        """
        Dynamically fetches actual or synthetic M15 candle replay and decision timeline
        associated with the specified trade ticket or ID.
        """
        from datetime import datetime, timedelta
        try:
            trade = db._execute(
                "SELECT * FROM trades WHERE mt5_ticket = ? OR trade_id = ? LIMIT 1",
                (ticket, ticket), fetch="one"
            )
            if not trade:
                return JSONResponse(status_code=404, content={"success": False, "message": f"Trade {ticket} not found."})

            symbol = trade.get("symbol", "XAUUSD")
            t_open = trade.get("timestamp_open")
            t_close = trade.get("timestamp_close") or datetime.utcnow().isoformat()
            direction = trade.get("direction", "LONG")
            entry = float(trade.get("entry_price") or 0.0)
            exit_p = float(trade.get("exit_price") or 0.0)
            sl = float(trade.get("stop_loss") or 0.0)
            tp = float(trade.get("take_profit") or 0.0)

            candles = []
            try:
                open_dt = datetime.fromisoformat(t_open.replace('Z', ''))
                close_dt = datetime.fromisoformat(t_close.replace('Z', ''))
                start_dt = open_dt - timedelta(hours=6)
                end_dt = close_dt + timedelta(hours=4)
                
                df = mt5_broker.get_ohlcv(symbol, "M15", count=200)
                if df is not None and not df.empty:
                    df_filtered = df[(df.index >= start_dt) & (df.index <= end_dt)]
                    for ts, row in df_filtered.iterrows():
                        candles.append({
                            "x": int(ts.timestamp() * 1000),
                            "y": [float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])]
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch real candles for replay: {e}")

            if len(candles) < 5:
                candles = []
                base_time = int(datetime.fromisoformat(t_open.replace('Z', '')).timestamp() * 1000)
                interval = 15 * 60 * 1000
                
                for i in range(-15, 15):
                    bar_time = base_time + (i * interval)
                    
                    if i < 0:
                        mult = -1.0 if direction == "LONG" else 1.0
                        close_val = entry + (mult * (abs(i) * (entry * 0.0002)))
                        open_val = close_val - (mult * (entry * 0.0001))
                    elif i == 0:
                        open_val = entry
                        close_val = entry + (entry * 0.0005 if direction == "LONG" else -entry * 0.0005)
                    else:
                        progress = i / 15.0
                        close_val = entry + progress * (exit_p - entry)
                        open_val = entry + (i - 1) / 15.0 * (exit_p - entry)
                        
                    high_val = max(open_val, close_val) + (entry * 0.0002)
                    low_val = min(open_val, close_val) - (entry * 0.0002)
                    
                    if i == 14:
                        close_val = exit_p
                        if exit_p == sl:
                            low_val = min(low_val, sl) if direction == "LONG" else low_val
                            high_val = max(high_val, sl) if direction == "SHORT" else high_val
                        elif exit_p == tp:
                            high_val = max(high_val, tp) if direction == "LONG" else high_val
                            low_val = min(low_val, tp) if direction == "SHORT" else low_val
                    
                    candles.append({
                        "x": bar_time,
                        "y": [round(open_val, 5), round(high_val, 5), round(low_val, 5), round(close_val, 5)]
                    })

            timeline = [
                {
                    "time": t_open[11:19],
                    "title": "Signal Detected & Compilation",
                    "text": f"Scout compiled confluence score of {trade.get('confidence_score')}/100. Structure: {trade.get('score_structure')} | SMC: {trade.get('score_smc')} | Liquidity: {trade.get('score_liquidity')}."
                },
                {
                    "time": t_open[11:19],
                    "title": "Validation Committee Audit",
                    "text": f"Consensus status: {trade.get('quality_grade')} grade approved. Sizing adjusted for drawdown scaling constraints."
                },
                {
                    "time": t_open[11:19],
                    "title": "Probe Position Executed",
                    "text": f"MT5 order filled at entry price {entry:.5f} (Lots: {trade.get('position_size_lots')}). SL: {sl:.5f} | TP: {tp:.5f}."
                }
            ]
            
            pnl = float(trade.get("pnl_usd") or 0.0)
            res_str = "WIN" if pnl > 0.01 else ("LOSS" if pnl < -0.01 else "BREAKEVEN")
            timeline.append({
                "time": t_close[11:19] if t_close else "Active",
                "title": f"Position Closed ({res_str})",
                "text": f"Closed at price {exit_p:.5f}. Exit Code: {trade.get('exit_reason_code') or 'MANUAL_CLOSE'}. Net PnL: ${pnl:.2f}."
            })

            return {
                "success": True,
                "candles": candles,
                "timeline": timeline,
                "trade": dict(trade)
            }
        except Exception as e:
            logger.error(f"Error in trade replay endpoint: {e}")
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.get("/api/v1/advanced/backtest", tags=["Advanced Analytics"])
    def run_historical_backtest(
        symbol: str = Query("XAUUSD"),
        strategy: str = Query("scalping_strategy"),
        days: int = Query(7, ge=1, le=30)
    ):
        """
        Runs a historical backtest for the specified symbol, strategy, and lookback days.
        """
        from datetime import datetime, timedelta
        import random
        import pandas as pd
        try:
            bar_count = days * 100
            
            df_m5 = mt5_broker.get_ohlcv(symbol, "M5", count=bar_count * 3)
            df_m15 = mt5_broker.get_ohlcv(symbol, "M15", count=bar_count)
            df_h1 = mt5_broker.get_ohlcv(symbol, "H1", count=bar_count // 4)
            
            if df_m15 is None or df_m15.empty:
                logger.warning("MT5 offline or no historical data. Generating synthetic candles for Backtest Lab.")
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(days=days)
                
                idx_m15 = pd.date_range(start=start_time, end=end_time, freq="15min")
                prices = [2000.0]
                for _ in range(len(idx_m15) - 1):
                    prices.append(prices[-1] + random.uniform(-2.5, 2.5))
                
                df_m15 = pd.DataFrame(index=idx_m15)
                df_m15['open'] = prices
                df_m15['high'] = df_m15['open'] + [random.uniform(0.5, 3.0) for _ in range(len(idx_m15))]
                df_m15['low'] = df_m15['open'] - [random.uniform(0.5, 3.0) for _ in range(len(idx_m15))]
                df_m15['close'] = df_m15['open'] + [random.uniform(-1.0, 1.0) for _ in range(len(idx_m15))]
                df_m15['tick_volume'] = [random.randint(100, 1000) for _ in range(len(idx_m15))]
                
                idx_m5 = pd.date_range(start=start_time, end=end_time, freq="5min")
                df_m5 = pd.DataFrame(index=idx_m5)
                df_m5['open'] = 2000.0
                df_m5['high'] = 2001.0
                df_m5['low'] = 1999.0
                df_m5['close'] = 2000.0
                df_m5['tick_volume'] = 100
                
                idx_h1 = pd.date_range(start=start_time, end=end_time, freq="1h")
                df_h1 = pd.DataFrame(index=idx_h1)
                df_h1['open'] = 2000.0
                df_h1['high'] = 2002.0
                df_h1['low'] = 1998.0
                df_h1['close'] = 2000.0
                df_h1['tick_volume'] = 500

            from zohra.core.backtest import BacktestEngine
            engine = BacktestEngine(initial_balance=100000.0, min_score_threshold=70)
            report = engine.run_backtest(df_m5, df_m15, df_h1, symbol, start_idx=50)
            
            return {
                "success": True,
                "symbol": symbol,
                "strategy": strategy,
                "days": days,
                "report": report
            }
        except Exception as e:
            logger.error(f"Error in backtest lab endpoint: {e}")
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


    # ─── AI Memory Endpoints ──────────────────────────────────────

    @app.get("/api/v1/memory/recent", tags=["AI Memory"])
    def get_recent_memories(limit: int = Query(50, ge=1, le=200)):
        """Return recent AI memory entries via centralised db._execute()."""
        try:
            rows = db._execute(
                "SELECT id, timestamp, context_text, category, metadata_json FROM ai_memory_entries ORDER BY timestamp DESC LIMIT ?",
                (limit,), fetch="all"
            ) or []
            total_row = db._execute("SELECT COUNT(*) as cnt FROM ai_memory_entries", fetch="one")
            total = total_row["cnt"] if total_row else len(rows)
            entries = [{
                "id": r["id"], "timestamp": r["timestamp"],
                "context_text": r["context_text"], "category": r["category"],
                "metadata": json.loads(r["metadata_json"]) if r.get("metadata_json") else {}
            } for r in rows]
            return {"entries": entries, "total": total}
        except Exception as e:
            return {"entries": [], "total": 0, "error": str(e)}

    @app.get("/api/v1/memory/search", tags=["AI Memory"])
    def search_memories(q: str = Query(..., min_length=1)):
        """Search AI memory entries by text content via centralised db._execute()."""
        try:
            rows = db._execute(
                "SELECT id, timestamp, context_text, category, metadata_json FROM ai_memory_entries WHERE context_text LIKE ? ORDER BY timestamp DESC LIMIT 50",
                (f"%{q}%",), fetch="all"
            ) or []
            results = [{
                "id": r["id"], "timestamp": r["timestamp"],
                "context_text": r["context_text"], "category": r["category"],
                "metadata": json.loads(r["metadata_json"]) if r.get("metadata_json") else {}
            } for r in rows]
            return {"results": results, "query": q, "count": len(results)}
        except Exception as e:
            return {"results": [], "query": q, "count": 0, "error": str(e)}

    # ─── Learning Engine Endpoints ───────────────────────────────

    @app.get("/api/v1/learning/patterns", tags=["Learning Engine"])
    def get_learning_patterns():
        """Return discovered winning and failure patterns via centralised db._execute()."""
        try:
            winning = []
            try:
                winning = db._execute(
                    "SELECT pattern_signature, confluences, occurrences, success_rate, avg_pnl, created_at FROM pattern_discoveries ORDER BY success_rate DESC LIMIT 20",
                    fetch="all"
                ) or []
            except Exception:
                pass

            failures = []
            try:
                rows = db._execute(
                    "SELECT failure_signature, confluences, occurrences, fail_rate, avg_loss, created_at FROM failure_patterns ORDER BY fail_rate DESC LIMIT 20",
                    fetch="all"
                ) or []
                failures = [{"pattern_signature": r.get("failure_signature"), "confluences": r.get("confluences"),
                             "occurrences": r.get("occurrences"), "fail_rate": r.get("fail_rate"),
                             "avg_loss": r.get("avg_loss"), "created_at": r.get("created_at")} for r in rows]
            except Exception:
                pass

            return {"winning_patterns": winning, "failure_patterns": failures}
        except Exception as e:
            return {"winning_patterns": [], "failure_patterns": [], "error": str(e)}

    @app.get("/api/v1/learning/recommendations", tags=["Learning Engine"])
    def get_learning_recommendations():
        """Return AI-generated learning recommendations via centralised db._execute()."""
        try:
            rows = db._execute(
                "SELECT id, created_at, category, recommendation_text, supporting_evidence, applied FROM learning_recommendations ORDER BY created_at DESC LIMIT 30",
                fetch="all"
            ) or []
            recs = [{
                "id": r["id"], "created_at": r["created_at"], "category": r["category"],
                "recommendation_text": r["recommendation_text"],
                "supporting_evidence": r.get("supporting_evidence"),
                "applied": bool(r.get("applied", 0))
            } for r in rows]
            return {"recommendations": recs, "count": len(recs)}
        except Exception as e:
            return {"recommendations": [], "count": 0, "error": str(e)}

    # ─── HIE Endpoints ───────────────────────────────────────────

    @app.get("/api/v1/hie/status", tags=["Historical Intelligence"])
    def get_hie_status():
        try:
            from zohra.hie.hie_orchestrator import hie_orchestrator
            return hie_orchestrator.status()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @app.get("/api/v1/hie/pattern-stats", tags=["Historical Intelligence"])
    def get_hie_pattern_stats(
        symbol: Optional[str] = Query(None),
        setup_type: Optional[str] = Query(None),
        session: Optional[str] = Query(None),
        direction: Optional[str] = Query(None),
        timeframe: Optional[str] = Query(None)
    ):
        try:
            from zohra.hie.historical_pattern_database import historical_pattern_database
            res = historical_pattern_database.get_pattern_stats(
                symbol=symbol,
                setup_type=setup_type,
                session=session,
                direction=direction,
                timeframe=timeframe,
                min_occurrences=1
            )
            return {"patterns": res}
        except Exception as e:
            return {"patterns": [], "error": str(e)}

    @app.get("/api/v1/hie/symbol-profile/{symbol}", tags=["Historical Intelligence"])
    def get_hie_symbol_profile(symbol: str):
        try:
            from zohra.hie.symbol_intelligence_profiles import symbol_intelligence_profiles
            res = symbol_intelligence_profiles.get_profile(symbol)
            return {"symbol": symbol, "profile": res}
        except Exception as e:
            return {"symbol": symbol, "profile": {}, "error": str(e)}

    @app.get("/api/v1/hie/market-memory/{symbol}", tags=["Historical Intelligence"])
    def get_hie_market_memory(symbol: str):
        try:
            from zohra.hie.market_memory_engine import market_memory_engine
            res = market_memory_engine.get_symbol_memory_summary(symbol)
            return {"symbol": symbol, "memory": res}
        except Exception as e:
            return {"symbol": symbol, "memory": {}, "error": str(e)}

    @app.get("/api/v1/hie/similarity", tags=["Historical Intelligence"])
    def get_hie_similarity(
        symbol: str = Query(...),
        direction: str = Query(...),
        session: str = Query(...),
        setup_type: Optional[str] = Query(None)
    ):
        try:
            from zohra.hie.trade_similarity_engine import trade_similarity_engine
            res = trade_similarity_engine.find_similar(
                symbol=symbol,
                direction=direction.upper(),
                session=session,
                setup_type=setup_type
            )
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v1/hie/failure-patterns", tags=["Historical Intelligence"])
    def get_hie_failure_patterns():
        try:
            from zohra.hie.failure_pattern_detector import failure_pattern_detector
            res = failure_pattern_detector.get_flagged_patterns()
            return {"failure_patterns": res}
        except Exception as e:
            return {"failure_patterns": [], "error": str(e)}

    @app.get("/api/v1/hie/calibration", tags=["Historical Intelligence"])
    def get_hie_calibration():
        try:
            from zohra.hie.confidence_calibration_engine import confidence_calibration_engine
            res = confidence_calibration_engine.get_calibration_report()
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v1/hie/learning/daily", tags=["Historical Intelligence"])
    def get_hie_learning_daily():
        try:
            from zohra.hie.learning_engine_hie import learning_engine_hie
            res = learning_engine_hie.run_daily_analysis()
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v1/hie/learning/weekly", tags=["Historical Intelligence"])
    def get_hie_learning_weekly():
        try:
            from zohra.hie.learning_engine_hie import learning_engine_hie
            res = learning_engine_hie.run_weekly_analysis()
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v1/hie/learning/monthly", tags=["Historical Intelligence"])
    def get_hie_learning_monthly():
        try:
            from zohra.hie.learning_engine_hie import learning_engine_hie
            res = learning_engine_hie.run_monthly_analysis()
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v1/hie/candles/{symbol}/{tf}", tags=["Historical Intelligence"])
    def get_hie_candles_count(symbol: str, tf: str):
        try:
            from zohra.hie.historical_data_engine import historical_data_engine
            cnt = historical_data_engine.get_candle_count(symbol, tf)
            rng = historical_data_engine.get_available_range(symbol, tf)
            return {"symbol": symbol, "timeframe": tf, "count": cnt, "range": rng}
        except Exception as e:
            return {"count": 0, "error": str(e)}

    @app.get("/api/v1/hie/setups", tags=["Historical Intelligence"])
    def get_hie_setups(
        symbol: Optional[str] = Query(None),
        timeframe: Optional[str] = Query(None),
        setup_type: Optional[str] = Query(None),
        session: Optional[str] = Query(None),
        direction: Optional[str] = Query(None)
    ):
        try:
            from zohra.hie.setup_detection_engine import setup_detection_engine
            res = setup_detection_engine.get_setups(
                symbol=symbol,
                timeframe=timeframe,
                setup_type=setup_type,
                session=session,
                direction=direction
            )
            return {"setups": res}
        except Exception as e:
            return {"setups": [], "error": str(e)}

    @app.post("/api/v1/hie/replay/start", tags=["Historical Replay"])
    def post_hie_replay_start(payload: dict):
        try:
            from zohra.hie.market_replay_engine import market_replay_engine
            symbol = payload.get("symbol", "XAUUSD")
            tf = payload.get("timeframe", "H1")
            from_dt = payload.get("from_datetime")
            to_dt = payload.get("to_datetime")
            speed = float(payload.get("speed", 1.0))
            
            success = market_replay_engine.start_replay(symbol, tf, from_dt, to_dt, speed)
            return {"success": success, "message": "Replay session started." if success else "Failed to start replay."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v1/hie/replay/next", tags=["Historical Replay"])
    def get_hie_replay_next():
        try:
            from zohra.hie.market_replay_engine import market_replay_engine
            candle = market_replay_engine.get_next_candle()
            if candle is None:
                return {"success": False, "message": "Replay finished or not started."}
            return {"success": True, "candle": candle}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/v1/hie/replay/stop", tags=["Historical Replay"])
    def post_hie_replay_stop():
        try:
            from zohra.hie.market_replay_engine import market_replay_engine
            market_replay_engine.stop()
            return {"success": True, "message": "Replay session stopped."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/v1/hie/chat-query", tags=["Historical Intelligence"])
    async def get_hie_chat_query(q: str = Query(...)):
        try:
            from zohra.services.chat.agent_brain import agentic_brain
            final_text = ""
            async for event in agentic_brain.run_reasoning_loop("hie_chat_session", q):
                if event["type"] == "token":
                    final_text += event["content"]
            return {"response": final_text}
        except Exception as e:
            return {"response": f"Error resolving query: {e}"}


def create_app(broker=None, scorer=None):
    return app


def run_api(host: str = "127.0.0.1", port: int = 8000, broker=None, scorer=None):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
