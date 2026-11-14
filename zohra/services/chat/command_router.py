import logging
import json
from typing import Dict, Any, Tuple, List
from zohra.db.schema import db
from zohra.services.chat.explain_layer import ExplainLayer

logger = logging.getLogger("zohra.services.chat.router")


def _safe_import_connector(name):
    """Safely import connector classes — never crash."""
    try:
        if name == "db":
            from zohra.api.connectors.db_connector import DBConnector
            return DBConnector()
        elif name == "engine":
            from zohra.api.connectors.engine_connector import EngineConnector
            return EngineConnector()
        elif name == "analytics":
            from zohra.api.connectors.analytics_connector import AnalyticsConnector
            return AnalyticsConnector()
    except Exception as e:
        logger.warning(f"Could not load connector '{name}': {e}")
    return None


class CommandRouter:
    """
    Routes parsed NLU intents to the proper connector layers,
    aggregates results, and returns natural language reasoning responses.
    Every connector call is wrapped in try/except — the chat NEVER crashes.
    """

    def __init__(self):
        self.db_conn = _safe_import_connector("db")
        self.engine_conn = _safe_import_connector("engine")
        self.analytics_conn = _safe_import_connector("analytics")
        self.explain_layer = ExplainLayer()

    def _gather_trading_context(self) -> Dict[str, Any]:
        """
        Gather a rich snapshot of the current trading state.
        This context is injected into every AI response so Zohra
        can answer ANY question intelligently.
        """
        context = {}

        # Account info
        try:
            from zohra.brokers.manager import broker_manager as mt5_broker
            info = mt5_broker.get_account_info()
            if info:
                context["account"] = {
                    "balance": info.get("balance", 0),
                    "equity": info.get("equity", 0),
                    "margin_free": info.get("margin_free", 0),
                    "profit": info.get("profit", 0),
                }
        except Exception:
            pass

        # Open positions
        try:
            open_trades = db.get_open_trades() or []
            context["open_positions"] = len(open_trades)
            context["open_trades_summary"] = [
                {"symbol": t.get("symbol"), "direction": t.get("direction"),
                 "pnl": t.get("pnl_usd", 0), "entry": t.get("entry_price")}
                for t in open_trades[:10]
            ]
        except Exception:
            context["open_positions"] = 0

        # Today's performance
        try:
            from zohra.analytics.performance import analytics
            daily = analytics.daily()
            context["today"] = {
                "trades": daily.get("total_trades", 0),
                "wins": daily.get("wins", 0),
                "losses": daily.get("losses", 0),
                "net_pnl": daily.get("net_pnl", 0),
                "win_rate": daily.get("win_rate_pct", 0),
            }
        except Exception:
            pass

        # Recent closed trades (last 5)
        try:
            closed = db.get_closed_trades(limit=5) or []
            context["recent_trades"] = [
                {"symbol": t.get("symbol"), "direction": t.get("direction"),
                 "pnl": t.get("pnl_usd", 0), "strategy": t.get("strategy_used", ""),
                 "score": t.get("confidence_score", 0)}
                for t in closed
            ]
        except Exception:
            pass

        # Engine state
        try:
            from zohra.config.settings import STATE
            context["engine_state"] = {
                "trading_enabled": STATE.trading_enabled,
                "halted": STATE.trading_halted,
                "halt_reason": STATE.halt_reason or "",
                "daily_trades": STATE.daily_trades,
                "daily_pnl": round(STATE.daily_pnl, 2),
            }
        except Exception:
            pass

        # AI memory (recent experiences)
        try:
            from zohra.memory.vector_store import ai_memory
            memories = ai_memory.query_experience("", limit=3)
            if memories:
                context["recent_memories"] = memories[:3]
        except Exception:
            pass

        return context

    def dispatch(self, intent: str, parameters: Dict[str, Any], raw_query: str = "") -> Tuple[str, Dict[str, Any]]:
        """
        Executes the requested intent action, gets the raw data payload,
        and returns a tuple of (human_readable_explanation, raw_data_payload).
        """
        legacy_trading_aliases = {
            "GET_POSITIONS": ("TRADING_QUERY", {"action": "get_positions"}),
            "CLOSE_ALL": ("TRADING_QUERY", {"action": "close_all"}),
            "CLOSE_PROFITABLE": ("TRADING_QUERY", {"action": "close_profitable"}),
            "HALT_TRADING": ("TRADING_QUERY", {"action": "halt"}),
            "RESUME_TRADING": ("TRADING_QUERY", {"action": "resume"}),
            "MODIFY_RISK": ("TRADING_QUERY", {"action": "modify_risk"}),
        }
        legacy_query_aliases = {
            "GET_PERFORMANCE": "ANALYTICS_QUERY",
            "EXPLAIN_REJECTION": "JOURNAL_QUERY",
            "EXPLAIN_TRADE": "JOURNAL_QUERY",
            "ANALYZE_MARKET": "RESEARCH_QUERY",
        }
        response_intent = intent
        if intent in legacy_trading_aliases:
            normalized_intent, defaults = legacy_trading_aliases[intent]
            parameters = {**defaults, **(parameters or {})}
            intent = normalized_intent
        elif intent in legacy_query_aliases:
            intent = legacy_query_aliases[intent]

        logger.info(f"Routing intent: {intent} | Parameters: {parameters}")
        data = {}

        try:
            from zohra.services.chat.agents import (
                trading_agent, risk_agent, analytics_agent, learning_agent,
                research_agent, memory_agent, task_agent, system_agent,
                social_media_agent, business_agent, personal_agent, security_agent
            )
            import os

            if intent == "TRADING_QUERY":
                action = parameters.get("action", "get_positions")
                if action == "get_positions":
                    data = trading_agent.get_positions_summary()
                elif action == "close_all":
                    data = trading_agent.close_positions("ALL")
                elif action == "close_profitable":
                    data = trading_agent.close_positions("PROFITABLE")
                elif action == "halt":
                    reason = parameters.get("reason", "Halted via Command Center")
                    from zohra.config.settings import STATE
                    STATE.trading_enabled = False
                    STATE.trading_halted = True
                    STATE.halt_reason = reason
                    db.log_system("WARNING", f"Trading HALTED via Command Center: {reason}", "CommandCenter")
                    data = {"success": True, "action": "halt", "reason": reason}
                elif action == "resume":
                    from zohra.config.settings import STATE
                    STATE.trading_enabled = True
                    STATE.trading_halted = False
                    STATE.halt_reason = ""
                    db.log_system("INFO", "Trading RESUMED via Command Center", "CommandCenter")
                    data = {"success": True, "action": "resume"}
                elif action == "modify_risk":
                    risk_pct = parameters.get("risk_pct")
                    if risk_pct is not None:
                        data = risk_agent.modify_risk(risk_pct)
                    else:
                        data = {"error": "Missing risk_pct parameter"}
                else:
                    data = trading_agent.get_positions_summary()

            elif intent == "ANALYTICS_QUERY":
                days = parameters.get("days", 30)
                data = {
                    "performance": analytics_agent.get_performance_analytics(days=days),
                    "strategies": analytics_agent.get_strategy_performance(days=days),
                    "pairs": analytics_agent.get_pair_performance(days=days)
                }

            elif intent == "JOURNAL_QUERY":
                ticket = parameters.get("ticket")
                symbol = parameters.get("symbol")
                from zohra.services.chat.tool_calling import query_trade_journal
                journal_data = query_trade_journal(ticket=ticket, symbol=symbol)
                data = json.loads(journal_data)

            elif intent == "MEMORY_QUERY":
                action = parameters.get("action", "search")
                query_text = parameters.get("query_text", "")
                if action == "store":
                    memory_id = memory_agent.add_preference(query_text)
                    data = {"success": True, "message": "Memory successfully recorded.", "memory_id": memory_id}
                else:
                    mems = memory_agent.search_memories(query_text)
                    data = {"memories": mems}

            elif intent == "RESEARCH_QUERY":
                symbol = parameters.get("symbol")
                
                # Check if it's a financial symbol or a general research topic
                is_symbol = False
                if symbol:
                    is_symbol = symbol.upper() in ["XAUUSD"]
                    
                if is_symbol:
                    from zohra.core.analytics_engines import gold_behavior_engine, market_condition_engine
                    from zohra.brokers.manager import broker_manager as mt5_broker
                    
                    df_m15 = mt5_broker.get_ohlcv(symbol, "M15", count=100)
                    market_cond = market_condition_engine.classify_market(df_m15)
                    
                    gold_analysis = {}
                    if symbol.upper() == "XAUUSD":
                        gold_analysis = gold_behavior_engine.analyze_gold_session()

                    data = {
                        "market_regime": research_agent.get_market_regime(symbol),
                        "symbol_profile": research_agent.get_symbol_profile(symbol),
                        "market_condition": market_cond,
                        "gold_behavior": gold_analysis
                    }
                else:
                    # Run general research orchestrator
                    topic = raw_query.lower().replace("research", "").replace("study", "").replace("compare", "").strip()
                    if not topic:
                        topic = "Smart Money Concepts"
                    
                    from zohra.core.research_orchestrator import research_orchestrator
                    import asyncio
                    import threading
                    
                    # Helper to run async code safely from synchronous method
                    def run_async(coro):
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            return asyncio.run(coro)
                        
                        result = []
                        def target():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                result.append(new_loop.run_until_complete(coro))
                            finally:
                                new_loop.close()
                                
                        t = threading.Thread(target=target)
                        t.start()
                        t.join()
                        return result[0]
                        
                    res = run_async(research_orchestrator.conduct_research(topic))
                    data = {
                        "general_research": True,
                        "topic": topic,
                        "report": res["report_md"],
                        "sources_count": res["sources_count"],
                        "claims_count": res["claims_count"]
                    }

            elif intent == "BACKTEST_QUERY":
                action = parameters.get("action", "run_backtest")
                symbol = parameters.get("symbol", "XAUUSD")
                
                from zohra.core.backtest import BacktestEngine
                from zohra.core.market_replay import market_replay_lab
                from zohra.brokers.manager import broker_manager as mt5_broker
                
                df_m5 = mt5_broker.get_ohlcv(symbol, "M5", count=500)
                df_m15 = mt5_broker.get_ohlcv(symbol, "M15", count=500)
                df_h1 = mt5_broker.get_ohlcv(symbol, "H1", count=500)
                
                if action == "run_backtest":
                    engine = BacktestEngine(initial_balance=100000.0)
                    report = engine.run_backtest(df_m5, df_m15, df_h1, symbol)
                    data = {"success": True, "report": report}
                elif action == "run_replay":
                    market_replay_lab.load_data(df_m15)
                    market_replay_lab.step_forward()
                    data = {
                        "success": True, 
                        "message": "Market Replay Lab initialized and stepped to first bar.", 
                        "current_idx": market_replay_lab.current_idx,
                        "total_bars": len(df_m15)
                    }
                elif action == "monte_carlo":
                    closed_trades = db.get_closed_trades(limit=100) or []
                    if not closed_trades:
                        closed_trades = [
                            {"pnl_usd": 150.0}, {"pnl_usd": -100.0}, {"pnl_usd": 300.0},
                            {"pnl_usd": -50.0}, {"pnl_usd": 200.0}, {"pnl_usd": -120.0}
                        ]
                    engine = BacktestEngine(initial_balance=100000.0)
                    mc_report = engine.run_monte_carlo(closed_trades)
                    data = {"success": True, "monte_carlo": mc_report}
                elif action == "sensitivity":
                    engine = BacktestEngine(initial_balance=100000.0)
                    sens_report = engine.run_sensitivity_analysis(df_m5, df_m15, df_h1, symbol, [70, 75, 80])
                    data = {"success": True, "sensitivity": sens_report}

            elif intent == "TASK_QUERY":
                action = parameters.get("action", "list")
                if action == "create":
                    title = parameters.get("title", "New Task")
                    data = task_agent.create_task(title)
                elif action == "complete":
                    task_id = parameters.get("task_id", 0)
                    success = task_agent.update_task_status(task_id, "completed")
                    data = {"success": success, "task_id": task_id}
                else:
                    data = {"tasks": task_agent.get_tasks()}

            elif intent == "SYSTEM_QUERY":
                from zohra.core.zohra_core import zohra_core
                try:
                    data = zohra_core.get_system_health()
                except Exception:
                    data = system_agent.get_system_health()

            elif intent == "FILE_QUERY":
                action = parameters.get("action", "list")
                file_path = parameters.get("file_path")
                if action == "read" and file_path:
                    # Sanitize path to prevent directory traversal
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    safe_path = os.path.normpath(os.path.join(project_root, file_path))
                    if safe_path.startswith(project_root) and os.path.exists(safe_path) and os.path.isfile(safe_path):
                        if os.path.getsize(safe_path) < 1024 * 50:
                            with open(safe_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read(4000)
                            data = {"file": file_path, "content": content}
                        else:
                            data = {"file": file_path, "error": "File size exceeds safety threshold (50KB)."}
                    else:
                        data = {"error": "Access denied or file does not exist."}
                else:
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    files = []
                    for root, dirs, filenames in os.walk(project_root):
                        if any(p in root for p in [".git", ".venv", "__pycache__", ".pytest_cache"]):
                            continue
                        for f in filenames:
                            if f.endswith((".py", ".txt", ".json", ".md", ".sh", ".ps1")):
                                rel = os.path.relpath(os.path.join(root, f), project_root)
                                files.append(rel)
                                if len(files) >= 50:
                                    break
                        if len(files) >= 50:
                            break
                    data = {"workspace_files": files}

            elif intent == "LEARNING_QUERY":
                data = {
                    "failures": learning_agent.get_failure_patterns(),
                    "recommendations": learning_agent.recommend_adjustments()
                }

            elif intent == "SOCIAL_MEDIA_QUERY":
                action = parameters.get("action", "generate_content")
                platform = parameters.get("platform", "instagram")
                topic = parameters.get("topic", raw_query)
                
                from zohra.core.social_orchestrator import social_orchestrator
                from zohra.core.social_scheduler import social_scheduler
                from zohra.core.social_memory import social_memory
                
                # Clean topic name
                clean_topic = topic.lower().replace("create", "").replace("generate", "").replace("post", "").replace("about", "").strip()
                if not clean_topic:
                    clean_topic = "Smart Money Concepts"
                    
                if action == "approve_post" or "approve" in raw_query.lower():
                    post_id = parameters.get("post_id", 1)
                    success = social_scheduler.approve_post(post_id)
                    data = {"success": success, "post_id": post_id}
                elif action == "list_queue" or "queue" in raw_query.lower() or "calendar" in raw_query.lower():
                    data = {"queue": social_memory.get_content_queue()}
                else:
                    campaign = social_orchestrator.create_campaign(platform, clean_topic)
                    data = {"success": True, "campaign": campaign}

            elif intent == "BUSINESS_QUERY":
                action = parameters.get("action", "list_projects")
                recipient = parameters.get("recipient", "publisher@example.com")
                subject = parameters.get("subject", "Quant Desk Pitch")
                body_prompt = parameters.get("body_prompt", raw_query)
                
                from zohra.core.business_orchestrator import business_orchestrator
                from zohra.core.email_manager import email_manager
                from zohra.core.business_memory import business_memory
                from zohra.core.project_manager import project_manager
                
                if action == "draft_email" or "draft" in raw_query.lower() or "email" in raw_query.lower():
                    draft = business_orchestrator.run_outreach_campaign(recipient, subject, body_prompt)
                    data = {"success": True, "draft": draft}
                elif action == "approve_email" or "approve" in raw_query.lower():
                    draft_id = parameters.get("draft_id", 1)
                    success = email_manager.approve_and_send(draft_id)
                    data = {"success": success, "draft_id": draft_id}
                elif action == "list_contacts" or "contact" in raw_query.lower():
                    data = {"contacts": business_memory.get_contacts()}
                else:
                    data = {"projects": project_manager.get_project_status(), "kpi_summary": business_orchestrator.get_kpi_metrics()}

            elif intent == "PERSONAL_QUERY":
                from zohra.core.personal_orchestrator import personal_orchestrator
                from zohra.core.personal_memory import personal_memory
                from zohra.core.task_manager import task_manager
                from zohra.core.goal_manager import goal_manager
                from zohra.core.habit_tracker import habit_tracker

                action  = parameters.get("action", "daily_briefing")
                title   = parameters.get("title", "Note")
                content = parameters.get("content", raw_query)
                due_at  = parameters.get("due_at", "")
                msg     = raw_query.lower()

                if action == "add_note" or "note" in msg:
                    note_id = personal_memory.add_note(title, content)
                    data = {"success": True, "note_id": note_id, "title": title}
                elif action == "schedule_reminder" or "remind" in msg:
                    rid = personal_memory.add_reminder(content or title, due_at or "Tomorrow")
                    data = {"success": True, "reminder_id": rid, "title": content or title}
                elif action == "add_goal" or ("add" in msg and "goal" in msg):
                    category = parameters.get("category", "PERSONAL")
                    data = personal_orchestrator.add_goal(content or title, category, due_at)
                elif action == "add_task" or ("add" in msg and "task" in msg) or ("create" in msg and "task" in msg):
                    priority = parameters.get("priority", "MEDIUM")
                    data = personal_orchestrator.add_task(content or title, priority, due_at)
                elif action == "complete_task" or ("complete" in msg or "done" in msg):
                    task_id = parameters.get("task_id", 0)
                    success = task_manager.complete(task_id)
                    data = {"success": success, "task_id": task_id}
                elif action == "log_habit" or "habit" in msg:
                    habit_name = content or title
                    data = habit_tracker.log(habit_name)
                elif action == "list_goals" or "goal" in msg:
                    data = goal_manager.get_summary()
                elif action == "list_reminders" or "reminder" in msg:
                    data = {"reminders": personal_memory.get_reminders()}
                elif action == "list_notes" or ("note" in msg and "show" in msg):
                    data = {"notes": personal_memory.get_notes()}
                else:
                    # Default: return full daily briefing
                    data = personal_orchestrator.generate_daily_briefing()

            elif intent == "MEMORY_QUERY":
                from zohra.core.memory_api import memory_api
                query = raw_query.lower().replace("remember", "").replace("recall", "").replace("what do you know about", "").strip()
                res = memory_api.recall(query)
                data = {
                    "success": True,
                    "recalled_memories": True,
                    "query": query,
                    "episodes": res["episodes"],
                    "semantic_contexts": res["semantic_contexts"]
                }

            elif intent == "TIMELINE_QUERY":
                from zohra.core.memory_api import memory_api
                timeline = memory_api.get_timeline()
                data = {
                    "success": True,
                    "timeline": timeline
                }

            elif intent == "INFRASTRUCTURE_QUERY":
                from zohra.core.infrastructure_orchestrator import infra_orchestrator
                from zohra.core.backup_manager import backup_manager

                action    = parameters.get("action", "health_report")
                service_id = parameters.get("service_id", "")
                backup_file = parameters.get("backup_file", "")

                if action == "health_report":
                    data = infra_orchestrator.generate_health_report()
                elif action == "list_services":
                    data = {"services": infra_orchestrator.get_all_services()}
                elif action == "restart_service" and service_id:
                    data = infra_orchestrator.restart_service(service_id)
                elif action == "stop_service" and service_id:
                    data = infra_orchestrator.stop_service(service_id)
                elif action == "backup":
                    data = backup_manager.create_backup(label="manual")
                elif action == "list_backups":
                    data = {"backups": backup_manager.list_backups()}
                elif action == "restore" and backup_file:
                    data = backup_manager.restore_backup(backup_file, dry_run=False)
                elif action == "cost_report":
                    data = infra_orchestrator.get_cost_summary()
                else:
                    data = infra_orchestrator.generate_health_report()

            elif intent == "ENGINE_CONTROL":
                action = parameters.get("action", "status")
                engines = parameters.get("engines", [])
                from zohra.services.chat.tool_calling import control_market_engines
                res_str = control_market_engines(action=action, engines=engines)
                data = json.loads(res_str)

            elif intent == "GENERAL_QUERY":
                data = {
                    "query": raw_query,
                    "trading_context": self._gather_trading_context()
                }

            else:
                data = {"error": f"Unknown command intent: {intent}"}


        except Exception as e:
            logger.error(f"Execution error on intent {intent}: {e}")
            data = {"error": f"Error executing command: {str(e)}"}

        # Generate response using Explainable AI layer
        explanation = self.explain_layer.synthesize(response_intent, data, raw_query)
        return explanation, data

# Instantiate singleton
command_router = CommandRouter()
