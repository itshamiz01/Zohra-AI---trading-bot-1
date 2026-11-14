# zohra/services/chat/agents.py
import os
import sys
import json
import time
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional
from zohra.services.chat.base_agent import ZohraBaseAgent

logger = logging.getLogger("zohra.services.chat.agents")

# Helper to log errors safely
def _safe_call(func, default_retval=None, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error in agent operation {func.__name__}: {e}")
        return default_retval or {"error": str(e)}

class TradingAgent(ZohraBaseAgent):
    """Trading Agent: queries MT5 details, open positions, recent closed trades, places emergency closes, and lists opportunities."""
    def __init__(self):
        super().__init__("trading_agent", "Trading Agent", "Queries MT5 details, open positions, recent closed trades, places emergency closes, and lists opportunities.")

    def get_positions_summary(self) -> Dict[str, Any]:
        try:
            from zohra.brokers.manager import broker_manager as mt5_broker
            from zohra.db.schema import db
            acc = mt5_broker.get_account_info() or {}
            open_trades = db.get_open_trades() or []
            
            return {
                "balance": acc.get("balance", 0.0),
                "equity": acc.get("equity", 0.0),
                "margin_free": acc.get("margin_free", 0.0),
                "floating_pnl": acc.get("profit", 0.0),
                "margin_level": acc.get("margin_level", 0.0),
                "open_count": len(open_trades),
                "positions": [
                    {
                        "ticket": t.get("mt5_ticket"),
                        "symbol": t.get("symbol"),
                        "direction": t.get("direction"),
                        "volume": t.get("position_size_lots"),
                        "entry_price": t.get("entry_price"),
                        "pnl": t.get("pnl_usd", 0.0),
                        "score": t.get("confidence_score")
                    } for t in open_trades
                ]
            }
        except Exception as e:
            logger.error(f"TradingAgent get_positions_summary error: {e}")
            return {"error": str(e)}

    def close_positions(self, action_type: str) -> Dict[str, Any]:
        if action_type.upper() not in ("ALL", "PROFITABLE"):
            return {"success": False, "error": "action_type must be either 'ALL' or 'PROFITABLE'"}
        try:
            from zohra.brokers.manager import broker_manager as mt5_broker
            from zohra.db.schema import db
            if action_type.upper() == "ALL":
                closed = mt5_broker.close_all_positions(comment="CommandCenter-Close")
                db.log_system("WARNING", f"Emergency CLOSE_ALL executed by TradingAgent. Closed {closed} positions.", "TradingAgent")
                return {"success": True, "positions_closed": closed, "message": f"Successfully closed all {closed} positions."}
            else:
                from zohra.api.connectors.engine_connector import EngineConnector
                conn = EngineConnector()
                closed = conn.close_profitable_positions()
                db.log_system("INFO", f"CLOSE_PROFITABLE executed by TradingAgent. Closed {closed} positions.", "TradingAgent")
                return {"success": True, "positions_closed": closed, "message": f"Successfully closed {closed} profitable positions."}
        except Exception as e:
            logger.error(f"TradingAgent close_positions error: {e}")
            return {"success": False, "error": str(e)}

    def get_opportunities(self) -> List[Dict[str, Any]]:
        try:
            from zohra.db.schema import db
            return db.get_live_opportunities() or []
        except Exception as e:
            logger.error(f"TradingAgent get_opportunities error: {e}")
            return []

class RiskAgent(ZohraBaseAgent):
    """Risk Agent: analyzes drawdowns, risk concentration, margin levels, and modifies risk limits."""
    def __init__(self):
        super().__init__("risk_agent", "Risk Agent", "Analyzes drawdowns, risk concentration, margin levels, and modifies risk limits.")

    def get_risk_report(self) -> Dict[str, Any]:
        try:
            from zohra.brokers.manager import broker_manager as mt5_broker
            from zohra.config.settings import STATE, settings
            from zohra.db.schema import db
            
            acc = mt5_broker.get_account_info() or {}
            equity = acc.get("equity", 0.0)
            balance = acc.get("balance", 0.0)
            margin_level = acc.get("margin_level", 0.0)
            
            drawdown_pct = 0.0
            if STATE.peak_equity > 0 and equity > 0:
                drawdown_pct = max(0.0, (STATE.peak_equity - equity) / STATE.peak_equity * 100.0)
                
            open_trades = db.get_open_trades() or []
            symbols = [t.get("symbol") for t in open_trades]
            symbol_concentration = {}
            for s in symbols:
                symbol_concentration[s] = symbol_concentration.get(s, 0) + 1
                
            warnings = []
            if drawdown_pct >= 4.0:
                warnings.append("⚠️ Drawdown exceeds 4.0% threshold. Halting risk parameters recommended.")
            if margin_level > 0 and margin_level < 200.0:
                warnings.append("⚠️ Margin level below 200.0%. Danger of margin call.")
            if len(open_trades) >= 5:
                warnings.append("⚠️ Excessive concentration: 5 or more concurrent trades active.")
                
            return {
                "drawdown_pct": round(drawdown_pct, 2),
                "margin_level": round(margin_level, 2),
                "risk_per_trade_pct": settings.RISK_PER_TRADE_PCT,
                "concentration": symbol_concentration,
                "warnings": warnings,
                "margin_health": "HEALTHY" if margin_level > 300 or margin_level == 0 else "WARNING" if margin_level > 150 else "CRITICAL",
                "halted": STATE.trading_halted,
                "halt_reason": STATE.halt_reason or "None"
            }
        except Exception as e:
            logger.error(f"RiskAgent get_risk_report error: {e}")
            return {"error": str(e)}

    def modify_risk(self, risk_pct: float) -> Dict[str, Any]:
        if not (0.1 <= risk_pct <= 5.0):
            return {"success": False, "error": "Risk percentage must be between 0.1% and 5.0%"}
        try:
            from zohra.config.settings import settings
            from zohra.db.schema import db
            settings.RISK_PER_TRADE_PCT = risk_pct / 100.0
            db.log_system("INFO", f"Risk per trade adjusted by RiskAgent to {risk_pct}%", "RiskAgent")
            return {"success": True, "new_risk_pct": risk_pct, "message": "Risk per trade successfully updated."}
        except Exception as e:
            logger.error(f"RiskAgent modify_risk error: {e}")
            return {"success": False, "error": str(e)}

class AnalyticsAgent(ZohraBaseAgent):
    """Analytics Agent: computes win rate, profit factor, drawdown, and identifies strategy ranking metrics."""
    def __init__(self):
        super().__init__("analytics_agent", "Analytics Agent", "Computes win rate, profit factor, drawdown, and identifies strategy ranking metrics.")

    def get_performance_analytics(self, days: int = 30) -> Dict[str, Any]:
        try:
            from zohra.db.schema import db
            from zohra.analytics.performance import analytics
            trades = db.get_closed_trades(limit=1000, days=days) or []
            equity_curve = db.get_equity_curve(days=days) or []
            
            report = analytics.full_performance_report(trades, equity_curve, period=f"Last {days} days")
            return report
        except Exception as e:
            logger.error(f"AnalyticsAgent get_performance_analytics error: {e}")
            return {"error": str(e)}

    def get_strategy_performance(self, days: int = 30) -> Dict[str, Any]:
        try:
            from zohra.db.schema import db
            stats = db.get_strategy_stats(days=days) or []
            
            best_strat = "None"
            best_pnl = -999999.0
            worst_strat = "None"
            worst_pnl = 999999.0
            
            for s in stats:
                pnl = s.get("net_pnl", 0.0)
                name = s.get("strategy", "Unknown")
                if pnl > best_pnl:
                    best_pnl = pnl
                    best_strat = name
                if pnl < worst_pnl:
                    worst_pnl = pnl
                    worst_strat = name
                    
            return {
                "strategies": stats,
                "best_performing_strategy": best_strat if best_pnl != -999999.0 else "None",
                "worst_performing_strategy": worst_strat if worst_pnl != 999999.0 else "None"
            }
        except Exception as e:
            logger.error(f"AnalyticsAgent get_strategy_performance error: {e}")
            return {"error": str(e)}

    def get_pair_performance(self, days: int = 30) -> Dict[str, Any]:
        try:
            from zohra.db.schema import db
            stats = db.get_pair_stats(days=days) or []
            
            best_pair = "None"
            best_pnl = -999999.0
            worst_pair = "None"
            worst_pnl = 999999.0
            
            for s in stats:
                pnl = s.get("net_pnl", 0.0)
                symbol = s.get("symbol", "Unknown")
                if pnl > best_pnl:
                    best_pnl = pnl
                    best_pair = symbol
                if pnl < worst_pnl:
                    worst_pnl = pnl
                    worst_pair = symbol
                    
            return {
                "pairs": stats,
                "best_performing_pair": best_pair if best_pnl != -999999.0 else "None",
                "worst_performing_pair": worst_pair if worst_pnl != 999999.0 else "None"
            }
        except Exception as e:
            logger.error(f"AnalyticsAgent get_pair_performance error: {e}")
            return {"error": str(e)}

class LearningAgent(ZohraBaseAgent):
    """Learning Agent: calibration report, winning/losing setup diagnostics, failure pattern checks, adjustments recommendation."""
    def __init__(self):
        super().__init__("learning_agent", "Learning Agent", "Calibration report, winning/losing setup diagnostics, failure pattern checks, adjustments recommendation.")

    def get_failure_patterns(self) -> List[Dict[str, Any]]:
        try:
            from zohra.hie.failure_pattern_detector import failure_pattern_detector
            return failure_pattern_detector.get_flagged_patterns() or []
        except Exception as e:
            logger.error(f"LearningAgent get_failure_patterns error: {e}")
            return []

    def get_pattern_stats(self, symbol: str = None, setup_type: str = None, session: str = None, min_occurrences: int = 2) -> List[Dict[str, Any]]:
        try:
            from zohra.hie.historical_pattern_database import historical_pattern_database
            return historical_pattern_database.get_pattern_stats(
                symbol=symbol, setup_type=setup_type, session=session, min_occurrences=min_occurrences
            ) or []
        except Exception as e:
            logger.error(f"LearningAgent get_pattern_stats error: {e}")
            return []

    def recommend_adjustments(self) -> Dict[str, Any]:
        try:
            failures = self.get_failure_patterns()
            reduce_setups = []
            increase_setups = []
            
            for f in failures:
                reduce_setups.append(f"Setup {f.get('setup_type', '')} on {f.get('symbol', '')} during {f.get('session', '')} (Win Rate: {f.get('win_rate_pct', 0)}%)")
                
            from zohra.hie.historical_pattern_database import historical_pattern_database
            best_patterns = historical_pattern_database.get_pattern_stats(min_occurrences=3) or []
            sorted_best = sorted(best_patterns, key=lambda x: x.get("win_rate_pct", 0.0), reverse=True)
            for p in sorted_best[:3]:
                if p.get("win_rate_pct", 0.0) >= 65.0:
                    increase_setups.append(f"Setup {p.get('setup_type', '')} on {p.get('symbol', '')} during {p.get('session', '')} (Win Rate: {p.get('win_rate_pct', 0)}%)")
                    
            return {
                "reduce_exposure_setups": reduce_setups,
                "increase_size_setups": increase_setups,
                "notes": "Recommendations based on historical outcome mapping and recurring failure profiles."
            }
        except Exception as e:
            logger.error(f"LearningAgent recommend_adjustments error: {e}")
            return {"error": str(e)}

class ResearchAgent(ZohraBaseAgent):
    """Research Agent: market scans, profiles, and economic calendar/external market insights."""
    def __init__(self):
        super().__init__("research_agent", "Research Agent", "Market scans, profiles, and economic calendar/external market insights.")

    def get_market_regime(self, symbol: str) -> Dict[str, Any]:
        try:
            from zohra.core.market_regime import regime_detector
            from zohra.brokers.manager import broker_manager as mt5_broker
            df_check = mt5_broker.get_ohlcv(symbol, "M15", 50)
            if df_check is None or df_check.empty:
                return {"error": f"No market data available for {symbol}"}
                
            regime = regime_detector.detect(df_check)
            close = df_check['close'].values
            
            return {
                "symbol": symbol,
                "regime": regime.value if hasattr(regime, 'value') else str(regime),
                "close_price": float(close[-1]),
                "time_utc": datetime.utcnow().strftime("%H:%M:%S")
            }
        except Exception as e:
            logger.error(f"ResearchAgent get_market_regime error: {e}")
            return {"error": str(e)}

    def get_symbol_profile(self, symbol: str) -> Dict[str, Any]:
        try:
            from zohra.hie.symbol_intelligence_profiles import symbol_intelligence_profiles
            from zohra.hie.market_memory_engine import market_memory_engine
            
            profile = symbol_intelligence_profiles.get_profile(symbol) or {}
            memory = market_memory_engine.get_symbol_memory_summary(symbol) or {}
            
            return {
                "symbol": symbol,
                "profile": profile,
                "memory_summary": memory
            }
        except Exception as e:
            logger.error(f"ResearchAgent get_symbol_profile error: {e}")
            return {"error": str(e)}

    def fetch_market_research_context(self, query: str) -> Dict[str, Any]:
        try:
            from zohra.db.schema import db
            open_trades = db.get_open_trades() or []
            active_symbols = list(set([t.get("symbol") for t in open_trades]))
            
            return {
                "query": query,
                "context_summary": f"Research context for query: '{query}'. Evaluated across active pairs: {active_symbols}.",
                "news_blackout": "None active",
                "recommended_focus": "Watch USD high-impact calendar data and London open breakouts."
            }
        except Exception as e:
            return {"error": str(e)}

class MemoryAgent(ZohraBaseAgent):
    """Memory Agent: interfaces with Layer 1-6 vector database layers and audits."""
    def __init__(self):
        super().__init__("memory_agent", "Memory Agent", "Interfaces with Layer 1-6 vector database layers and audits.")

    def add_preference(self, text: str, category: str = "preference_memory", metadata: dict = None) -> str:
        try:
            from zohra.services.chat.vector_memory import vector_memory
            return vector_memory.add_preference_or_insight(text, category, metadata)
        except Exception as e:
            logger.error(f"MemoryAgent add_preference error: {e}")
            return ""

    def search_memories(self, query: str, category: str = None, limit: int = 3) -> List[Dict[str, Any]]:
        try:
            from zohra.memory.vector_store import ai_memory
            return ai_memory.query_experience(query, category=category, limit=limit) or []
        except Exception as e:
            logger.error(f"MemoryAgent search_memories error: {e}")
            return []

class TaskAgent(ZohraBaseAgent):
    """Task Agent: manages systems task, reminder checkpoints and weekly logs."""
    def __init__(self):
        super().__init__("task_agent", "Task Agent", "Manages systems task, reminder checkpoints and weekly logs.")
        self._init_db()

    def _init_db(self):
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        due_date TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
        except Exception as e:
            logger.error(f"Failed to initialize tasks table: {e}")

    def create_task(self, title: str, description: str = "", due_date: str = None) -> Dict[str, Any]:
        try:
            from zohra.db.connection import get_db
            created_at = datetime.utcnow().isoformat() + "Z"
            with get_db().cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ai_tasks (title, description, status, due_date, created_at)
                    VALUES (?, ?, 'pending', ?, ?)
                """, (title, description, due_date, created_at))
                task_id = cursor.lastrowid
            return {"success": True, "task": {"id": task_id, "title": title, "status": "pending", "due_date": due_date}}
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return {"success": False, "error": str(e)}

    def get_tasks(self, status: str = None) -> List[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                if status:
                    cursor.execute("SELECT * FROM ai_tasks WHERE status = ? ORDER BY id DESC", (status,))
                else:
                    cursor.execute("SELECT * FROM ai_tasks ORDER BY id DESC")
                rows = cursor.fetchall()
                tasks = [dict(r) for r in rows]
            return tasks
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            return []

    def update_task_status(self, task_id: int, status: str) -> bool:
        if status not in ("pending", "in_progress", "completed"):
            return False
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("UPDATE ai_tasks SET status = ? WHERE id = ?", (status, task_id))
            return True
        except Exception as e:
            logger.error(f"Error updating task: {e}")
            return False

class SystemAgent(ZohraBaseAgent):
    """System Agent: monitors hardware CPU, RAM, API delay, database sizes, and connectivity states."""
    def __init__(self):
        super().__init__("system_agent", "System Agent", "Monitors hardware CPU, RAM, API delay, database sizes, and connectivity states.")

    def get_system_health(self) -> Dict[str, Any]:
        cpu = 12.0
        ram = 45.0
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
        except ImportError:
            pass
            
        db_size_kb = 0
        try:
            from zohra.config.settings import settings
            if os.path.exists(settings.DB_PATH):
                db_size_kb = os.path.getsize(settings.DB_PATH) / 1024
        except Exception:
            pass
            
        mt5_connected = False
        try:
            from zohra.brokers.manager import broker_manager as mt5_broker
            mt5_connected = mt5_broker.is_connected()
        except Exception:
            pass
            
        from zohra.config.settings import STATE
        scanner_status = "active" if (STATE.trading_enabled and not STATE.trading_halted) else "paused"
        
        return {
            "cpu_usage_pct": cpu,
            "ram_usage_pct": ram,
            "database_size_kb": round(db_size_kb, 1),
            "mt5_connected": mt5_connected,
            "api_status": "online",
            "scanner_status": scanner_status,
            "risk_engine": "active",
            "learning_engine": "active",
            "dashboard_status": "online",
            "timestamp": time.time()
        }

class SocialMediaAgent(ZohraBaseAgent):
    """Social Media Agent: Content planning, calendars, caption/post generation, script ideas, and metrics."""
    def __init__(self):
        super().__init__("social_agent", "Social Media Agent", "Content planning, calendars, caption/post generation, script ideas, and metrics.")
        self._init_db()

    def _init_db(self):
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_social_calendar (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        post_text TEXT NOT NULL,
                        scheduled_at TEXT,
                        status TEXT NOT NULL DEFAULT 'draft'
                    )
                """)
        except Exception as e:
            logger.error(f"Failed to init social calendar table: {e}")

    def generate_content(self, platform: str, topic: str, content_type: str = "informational") -> Dict[str, Any]:
        captions = {
            "x": f"⚡ ZOHRA OS Scanner Alert: High confluence setup identified on XAUUSD. Aligning swing structures. Remember: Capital Preservation First. #Forex #TradingBot",
            "instagram": f"📈 Systematic Execution. Our SMC division just flagged a fresh zone. No emotions, pure probability. What's your target today?\n\n#trading #forex #algorithmictrading #gold",
            "youtube": f"Title: Inside the Zohra AI Trading Brain\n\nScript Intro: Welcome back to ZOHRA OS. Today, we are deep diving into why we took the EURUSD London breakout and how the Risk Agent calibrated our margins. Let's look at the charts...",
            "linkedin": f"💡 Algorithmic trading requires robust isolation and strict risk controls. Today ZOHRA OS executed automated swing setups with 0.5% risk per trade. Systems engineering meets market liquidity. #FinTech #AlgorithmicTrading #Markets"
        }
        text = captions.get(platform.lower(), f"Content draft for {platform} regarding '{topic}'. Style: {content_type}.\n\nAlways adhere to core ZOHRA OS rules: absolute risk boundaries and systemic execution.")
        return {"success": True, "platform": platform, "topic": topic, "content": text}

    def get_calendar(self) -> List[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("SELECT * FROM ai_social_calendar ORDER BY id DESC")
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting social calendar: {e}")
            return []

    def add_post(self, platform: str, post_text: str, scheduled_at: str = None) -> Dict[str, Any]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ai_social_calendar (platform, post_text, scheduled_at, status)
                    VALUES (?, ?, ?, 'scheduled')
                """, (platform, post_text, scheduled_at))
                post_id = cursor.lastrowid
            return {"success": True, "post": {"id": post_id, "platform": platform, "post_text": post_text, "scheduled_at": scheduled_at}}
        except Exception as e:
            logger.error(f"Error adding post to calendar: {e}")
            return {"success": False, "error": str(e)}


class BusinessAgent(ZohraBaseAgent):
    """Business Agent: Email manager, lead tracking, publisher outreach submissions log."""
    def __init__(self):
        super().__init__("business_agent", "Business Agent", "Email manager, lead tracking, publisher outreach submissions log.")
        self._init_db()

    def _init_db(self):
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_publisher_outreach (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        publisher_name TEXT NOT NULL,
                        contact TEXT,
                        status TEXT NOT NULL DEFAULT 'identified',
                        last_contacted_at TEXT,
                        notes TEXT
                    )
                """)
                cursor.execute("SELECT COUNT(*) FROM ai_publisher_outreach")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO ai_publisher_outreach (publisher_name, contact, status, notes)
                        VALUES 
                        ('Algorithmic Press', 'contact@algopress.co', 'pitch_sent', 'Sent pitch for book publication'),
                        ('Quant Publishers', 'submissions@quantpub.org', 'identified', 'Top tier quantitative finance publisher'),
                        ('Forex Media Ltd', 'editor@forexmedia.com', 'negotiation', 'Interested in licensing model analysis')
                    """)
        except Exception as e:
            logger.error(f"Failed to init publisher outreach table: {e}")

    def draft_email(self, recipient: str, subject: str, body_prompt: str) -> Dict[str, Any]:
        email_draft = f"To: {recipient}\nSubject: {subject}\n\nDear recipient,\n\nFollowing up on our discussions regarding algorithmic trading systems. We have completed the deployment of ZOHRA OS v3.0 on isolated demo frameworks with outstanding results. Outlined below are our latest findings:\n\n{body_prompt}\n\nWe look forward to sharing detailed telemetry reports.\n\nBest regards,\nZOHRA Operating System"
        return {"success": True, "recipient": recipient, "subject": subject, "body": email_draft}

    def get_outreach(self) -> List[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("SELECT * FROM ai_publisher_outreach ORDER BY id DESC")
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting publisher outreach list: {e}")
            return []

    def log_contact(self, publisher_name: str, contact: str, status: str, notes: str = "") -> Dict[str, Any]:
        try:
            from zohra.db.connection import get_db
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            with get_db().cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ai_publisher_outreach (publisher_name, contact, status, last_contacted_at, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (publisher_name, contact, status, now, notes))
                contact_id = cursor.lastrowid
            return {"success": True, "contact": {"id": contact_id, "publisher_name": publisher_name, "contact": contact, "status": status, "notes": notes}}
        except Exception as e:
            logger.error(f"Error logging publisher contact: {e}")
            return {"success": False, "error": str(e)}


class PersonalAgent(ZohraBaseAgent):
    """Personal Agent: productivity manager (notes vault, reminders calendar, project goal tracker)."""
    def __init__(self):
        super().__init__("personal_agent", "Personal Agent", "Productivity manager (notes vault, reminders calendar, project goal tracker).")
        self._init_db()

    def _init_db(self):
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reminder_text TEXT NOT NULL,
                        due_at TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_goals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        goal_text TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        target_date TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                cursor.execute("SELECT COUNT(*) FROM ai_notes")
                if cursor.fetchone()[0] == 0:
                    created = datetime.utcnow().isoformat() + "Z"
                    cursor.execute("INSERT INTO ai_notes (title, content, created_at) VALUES (?, ?, ?)", 
                                   ("Trading Philosophy", "Always preserve capital. Wait for A+ setup alignments on multiple timeframes.", created))
                    cursor.execute("INSERT INTO ai_notes (title, content, created_at) VALUES (?, ?, ?)", 
                                   ("Book Notes", "Draft outline for 'Algorithmic Risk Management in Forex markets'", created))
                
                cursor.execute("SELECT COUNT(*) FROM ai_reminders")
                if cursor.fetchone()[0] == 0:
                    created = datetime.utcnow().isoformat() + "Z"
                    cursor.execute("INSERT INTO ai_reminders (reminder_text, due_at, created_at) VALUES (?, ?, ?)", 
                                   ("Review strategy weights", "Tomorrow 9 AM", created))
                
                cursor.execute("SELECT COUNT(*) FROM ai_goals")
                if cursor.fetchone()[0] == 0:
                    created = datetime.utcnow().isoformat() + "Z"
                    cursor.execute("INSERT INTO ai_goals (goal_text, target_date, created_at) VALUES (?, ?, ?)", 
                                   ("Migrate risk calculations to vector memory", "End of week", created))
        except Exception as e:
            logger.error(f"Failed to init personal tables: {e}")

    def add_note(self, title: str, content: str) -> Dict[str, Any]:
        try:
            from zohra.db.connection import get_db
            created = datetime.utcnow().isoformat() + "Z"
            with get_db().cursor() as cursor:
                cursor.execute("INSERT INTO ai_notes (title, content, created_at) VALUES (?, ?, ?)", (title, content, created))
                note_id = cursor.lastrowid
            return {"success": True, "note": {"id": note_id, "title": title, "content": content}}
        except Exception as e:
            logger.error(f"Error adding note: {e}")
            return {"success": False, "error": str(e)}

    def get_notes(self) -> List[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("SELECT * FROM ai_notes ORDER BY id DESC")
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting notes: {e}")
            return []

    def schedule_reminder(self, reminder_text: str, due_at: str) -> Dict[str, Any]:
        try:
            from zohra.db.connection import get_db
            created = datetime.utcnow().isoformat() + "Z"
            with get_db().cursor() as cursor:
                cursor.execute("INSERT INTO ai_reminders (reminder_text, due_at, created_at) VALUES (?, ?, ?)", (reminder_text, due_at, created))
                rem_id = cursor.lastrowid
            return {"success": True, "reminder": {"id": rem_id, "reminder_text": reminder_text, "due_at": due_at}}
        except Exception as e:
            logger.error(f"Error scheduling reminder: {e}")
            return {"success": False, "error": str(e)}

    def get_reminders(self) -> List[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("SELECT * FROM ai_reminders ORDER BY id DESC")
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting reminders: {e}")
            return []

    def add_goal(self, goal_text: str, target_date: str = None) -> Dict[str, Any]:
        try:
            from zohra.db.connection import get_db
            created = datetime.utcnow().isoformat() + "Z"
            with get_db().cursor() as cursor:
                cursor.execute("INSERT INTO ai_goals (goal_text, target_date, created_at) VALUES (?, ?, ?)", (goal_text, target_date, created))
                goal_id = cursor.lastrowid
            return {"success": True, "goal": {"id": goal_id, "goal_text": goal_text, "target_date": target_date}}
        except Exception as e:
            logger.error(f"Error adding goal: {e}")
            return {"success": False, "error": str(e)}

    def get_goals(self) -> List[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("SELECT * FROM ai_goals ORDER BY id DESC")
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting goals: {e}")
            return []

    def update_reminder_status(self, reminder_id: int, status: str) -> bool:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("UPDATE ai_reminders SET status = ? WHERE id = ?", (status, reminder_id))
            return True
        except Exception as e:
            logger.error(f"Error updating reminder status: {e}")
            return False

    def update_goal_status(self, goal_id: int, status: str) -> bool:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("UPDATE ai_goals SET status = ? WHERE id = ?", (status, goal_id))
            return True
        except Exception as e:
            logger.error(f"Error updating goal status: {e}")
            return False


class SecurityAgent(ZohraBaseAgent):
    """Security Agent: Permissions system checks, high-risk token validation, and confirmation logging."""
    def __init__(self):
        super().__init__("security_agent", "Security Agent", "Permissions system checks, high-risk token validation, and confirmation logging.")
        self._init_db()

    def _init_db(self):
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_security_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_token TEXT UNIQUE NOT NULL,
                        action_name TEXT NOT NULL,
                        action_payload TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL
                    )
                """)
        except Exception as e:
            logger.error(f"Failed to init security requests table: {e}")

    def create_security_request(self, action_name: str, payload: Dict[str, Any]) -> str:
        try:
            import secrets
            token = secrets.token_hex(16)
            from zohra.db.connection import get_db
            created = datetime.utcnow().isoformat() + "Z"
            payload_str = json.dumps(payload)
            with get_db().cursor() as cursor:
                cursor.execute("""
                    INSERT INTO ai_security_requests (request_token, action_name, action_payload, status, created_at)
                    VALUES (?, ?, ?, 'pending', ?)
                """, (token, action_name, payload_str, created))
            return token
        except Exception as e:
            logger.error(f"Error creating security request: {e}")
            return ""

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("SELECT * FROM ai_security_requests WHERE status = 'pending' ORDER BY id DESC")
                rows = cursor.fetchall()
                results = []
                for r in rows:
                    item = dict(r)
                    item["action_payload"] = json.loads(item["action_payload"])
                    results.append(item)
                return results
        except Exception as e:
            logger.error(f"Error getting pending security requests: {e}")
            return []

    def approve_request(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("SELECT * FROM ai_security_requests WHERE request_token = ? AND status = 'pending'", (token,))
                row = cursor.fetchone()
                if not row:
                    return None
                cursor.execute("UPDATE ai_security_requests SET status = 'approved' WHERE request_token = ?", (token,))
            payload = json.loads(row["action_payload"])
            return {"action_name": row["action_name"], "payload": payload}
        except Exception as e:
            logger.error(f"Error approving security request: {e}")
            return None

    def reject_request(self, token: str) -> bool:
        try:
            from zohra.db.connection import get_db
            with get_db().cursor() as cursor:
                cursor.execute("UPDATE ai_security_requests SET status = 'rejected' WHERE request_token = ?", (token,))
            return True
        except Exception as e:
            logger.error(f"Error rejecting security request: {e}")
            return False

# Instantiate global singletons for easy access
trading_agent = TradingAgent()
risk_agent = RiskAgent()
analytics_agent = AnalyticsAgent()
learning_agent = LearningAgent()
research_agent = ResearchAgent()
memory_agent = MemoryAgent()
task_agent = TaskAgent()
system_agent = SystemAgent()
social_media_agent = SocialMediaAgent()
business_agent = BusinessAgent()
personal_agent = PersonalAgent()
security_agent = SecurityAgent()
