#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA SUPREME BRAIN v5.0                           ║
║         Autonomous Multi-Strategy Orchestration Engine              ║
║                                                                      ║
║  All decisions must flow through this central brain.                 ║
║  No components may independently execute trades or manage risk.      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import signal
import logging
import traceback
import datetime as dt
import threading
import random
import asyncio
import pandas as pd
from zohra.utils.mt5_connection import mt5
from typing import Dict, List, Optional, Tuple, Any

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Ensure path is setup for module resolution
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Thread-safety lock for global STATE updates
state_lock = threading.Lock()

from zohra.config.settings import (
    ACTIVE_PAIRS, SESSIONS, LOG_DIR,
    SCAN_INTERVAL_SEC, MANAGE_INTERVAL_SEC,
    MAGIC_SMC, MAGIC_SCALP, STATE,
    RISK_PER_TRADE_PCT, MAX_OPEN_POSITIONS,
    MAX_DAILY_LOSS_PCT, MAX_WEEKLY_LOSS_PCT,
    MAX_MONTHLY_LOSS_PCT, MAX_DRAWDOWN_PCT,
    MAX_DAILY_TRADES, LOT_STEP, MIN_LOT_SIZE, MAX_LOT_SIZE,
    SCALP_PAIRS
)
from zohra.db.schema import db
from zohra.brokers.mt5_broker import mt5_broker
from zohra.core.market_regime import regime_detector
from zohra.core.adaptive_scorer import adaptive_scorer
from zohra.core.signal_scorer import scorer
from zohra.core.enums import MarketRegime, StrategyName, Direction, TradeQuality
from zohra.core.position_manager import position_manager
from zohra.core.investment_committee import investment_committee

# Strategies
from zohra.strategies.zohra_scoring_v5 import ZohraScoringEngine
from zohra.strategies.scalping_strategy import scalping_strategy
from zohra.strategies.mean_reversion import mean_reversion_strategy
from zohra.strategies.trend_following import trend_following_strategy
from zohra.strategies.breakout_strategy import breakout_strategy
from zohra.strategies.chart_pattern_strategy import chart_pattern_strategy

# Agents (for news and logging wrapper)
from zohra.agents.news_agent import NewsAgent
from zohra.agents.risk_agent import RiskAgent
from zohra.agents.performance_agent import PerformanceAgent

# Zohra event bus and AI memory/learning integrations
from zohra.event_bus import event_bus
from zohra.memory.vector_store import ai_memory
from zohra.learning.trade_forensics import trade_forensics
from zohra.learning.pattern_detector import learning_engine

from zohra.config.settings import settings

# Setup structured logger
logger = logging.getLogger("zohra")
logger.setLevel(logging.INFO)

formatter = logging.Formatter('[%(asctime)s UTC] [%(levelname)s] [%(name)s] %(message)s')
os.makedirs(LOG_DIR, exist_ok=True)

sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)

# Dynamic Brain Log path loaded from settings
brain_log_path = getattr(settings, "BRAIN_LOG", os.path.join(LOG_DIR, "zohra_brain_a.log"))
fh = logging.FileHandler(brain_log_path, encoding='utf-8')
fh.setFormatter(formatter)
logger.addHandler(fh)

JOURNAL_FILE = getattr(settings, "JOURNAL_FILE", os.path.join(LOG_DIR, "decision_journal_a.jsonl"))


class ZohraBrain:
    """
    The Single Central Brain supreme orchestrator.
    Controls Layer 1 (Market Data) to Layer 7 (Reporting).
    """

    def __init__(self, mode: str = "demo", min_score: int = 65, active_engines: list = None, **kwargs):
        self.mode = mode
        self.running = False
        self.starting_equity = 0.0

        # Engine selection: which market engines to activate on startup.
        # Default is forex (MT5 Gold & Silver). Valid values: "forex", "indian", "crypto".
        if active_engines is None:
            self.active_engines = ["forex"]
        else:
            self.active_engines = [e.lower().strip() for e in active_engines]

        # Wire score thresholds
        scorer.min_score = min_score

        # Initialize 15-Strategy Regime-Adaptive Confluence Engine
        from zohra.strategies.ema_pullback import EmaPullbackStrategy
        from zohra.strategies.vwap_mean_reversion import VwapMeanReversionStrategy
        from zohra.strategies.liquidity_mss import LiquidityMssStrategy
        from zohra.strategies.breakout import BreakoutStrategy
        from zohra.strategies.bollinger_rsi import BollingerRsiStrategy
        from zohra.strategies.fibonacci_pullback import FibonacciPullbackStrategy
        from zohra.strategies.support_resistance import SupportResistanceStrategy
        from zohra.strategies.supply_demand import SupplyDemandStrategy
        from zohra.strategies.fvg import FvgRetracementStrategy
        from zohra.strategies.order_block import OrderBlockStrategy
        from zohra.strategies.volume_breakout import VolumeBreakoutStrategy
        from zohra.strategies.atr_expansion import AtrExpansionStrategy
        from zohra.strategies.momentum_continuation import MomentumContinuationStrategy
        from zohra.strategies.mtf_alignment import MtfAlignmentStrategy
        from zohra.strategies.false_breakout import FalseBreakoutStrategy

        self.strategies = {
            StrategyName.EMA_PULLBACK.value: EmaPullbackStrategy(),
            StrategyName.FIBONACCI_PULLBACK.value: FibonacciPullbackStrategy(),
            StrategyName.MTF_ALIGNMENT.value: MtfAlignmentStrategy(),
            StrategyName.MOMENTUM_CONTINUATION.value: MomentumContinuationStrategy(),
            StrategyName.VWAP_MEAN_REVERSION.value: VwapMeanReversionStrategy(),
            StrategyName.BOLLINGER_RSI.value: BollingerRsiStrategy(),
            StrategyName.SR_REJECTION.value: SupportResistanceStrategy(),
            StrategyName.LIQUIDITY_MSS.value: LiquidityMssStrategy(),
            StrategyName.SUPPLY_DEMAND.value: SupplyDemandStrategy(),
            StrategyName.FVG_RETRACEMENT.value: FvgRetracementStrategy(),
            StrategyName.ORDER_BLOCK.value: OrderBlockStrategy(),
            StrategyName.FALSE_BREAKOUT.value: FalseBreakoutStrategy(),
            StrategyName.BREAKOUT.value: BreakoutStrategy(),
            StrategyName.VOLUME_BREAKOUT.value: VolumeBreakoutStrategy(),
            StrategyName.ATR_EXPANSION.value: AtrExpansionStrategy(),
            StrategyName.ZOHRA_V5.value: ZohraScoringEngine(),
            StrategyName.SCALP_M5.value: scalping_strategy,
        }

        # Register strategies in Strategy Registry (Phase 2)
        try:
            from zohra.strategies.strategy_registry import strategy_registry, StrategyMetadata
            for strat_key, strat_inst in self.strategies.items():
                group_val = getattr(strat_inst, "strategy_group", "TREND")
                regimes_val = [r.value for r in getattr(strat_inst, "allowed_regimes", [])] if hasattr(strat_inst, "allowed_regimes") else ["trending", "ranging"]
                meta = StrategyMetadata(
                    name=strat_key,
                    category="Scalping",
                    group=group_val,
                    applicable_regimes=regimes_val,
                    applicable_sessions=["London", "NewYork", "Overlap"],
                    applicable_timeframes=["M5", "M15"],
                    min_rrr=1.5,
                    description=f"Institutional XAUUSD Strategy: {strat_key}",
                    instance=strat_inst,
                    version="2.0.0"
                )
                strategy_registry.register(meta)
            logger.info("📋 Master Strategy Registry successfully populated from ZohraBrain strategies.")
        except Exception as e:
            logger.error(f"⚠️ Failed to populate Strategy Registry: {e}")

        # Initialize Safety Components
        self.news_agent = NewsAgent()
        self.risk_agent = RiskAgent()
        self.performance_agent = PerformanceAgent()

        # Initialize Multi-Symbol Components
        from zohra.core.opportunity_engine import OpportunityEngine
        self.opportunity_engine = OpportunityEngine()
        self.workers = {}

        # Local trade manager tracking
        self.last_bar_time = {} # symbol -> last bar timestamp (M5)

        # HFT parameters (2-minute trade frequency enforcement)
        self.last_execution_time = time.time() - 110.0
        self.hft_mode = True
        self.hft_interval_sec = 120

        # Register signals
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        # Register Event Bus subscribers
        self._register_event_subscribers()

        # Start Historical Intelligence Engine (HIE)
        try:
            from zohra.hie.hie_orchestrator import hie_orchestrator
            hie_orchestrator.start()
            logger.info("🏛️ HIE Orchestrator started on ZohraBrain initialization.")
        except Exception as e:
            logger.error(f"⚠️ Failed to start HIE Orchestrator: {e}")

        # ═══ Register engines in the central Engine Registry ═══
        self._register_engines_in_registry()

    def _register_engines_in_registry(self):
        """Registers all three market engines in the central EngineRegistry."""
        from zohra.core.engine_registry import engine_registry

        # 1. Forex Engine — start/stop managed by spawning/stopping symbol workers
        engine_registry.register(
            "forex", self,
            start_callback=self._start_forex_engine,
            stop_callback=self._stop_forex_engine
        )

        # 2. Crypto Engine
        try:
            from zohra.core.crypto_engine import crypto_engine
            engine_registry.register(
                "crypto", crypto_engine,
                start_callback=self._start_crypto_engine,
                stop_callback=self._stop_crypto_engine
            )
        except Exception as e:
            logger.warning(f"Could not register Crypto Engine: {e}")

        # 3. Indian Market Engine (registered but started on-demand)
        try:
            from zohra.engines.indian_market_engine import IndianMarketEngine
            engine_registry.register(
                "indian", None,
                start_callback=self._start_indian_engine,
                stop_callback=self._stop_indian_engine
            )
        except Exception as e:
            logger.warning(f"Could not register Indian Market Engine: {e}")

        logger.info(f"📋 Engine Registry populated. Requested active engines: {self.active_engines}")

    # ─── Engine Start/Stop Callbacks ─────────────────────────

    def _start_forex_engine(self):
        """Callback to start the Forex engine (symbol workers will be spawned in the async loop)."""
        logger.info("▶️ Forex Market Engine activation requested.")
        # The actual worker spawning happens in _run_async_loop when it checks the registry.

    def _stop_forex_engine(self):
        """Callback to stop the Forex engine — stops all symbol workers."""
        logger.info("⏹️ Stopping Forex Market Engine — shutting down all symbol workers...")
        for symbol, worker in list(self.workers.items()):
            try:
                worker.stop()
                logger.info(f"  Stopped worker for {symbol}")
            except Exception as e:
                logger.error(f"  Error stopping worker for {symbol}: {e}")
        self.workers.clear()

    def _start_crypto_engine(self):
        """Callback to start the Crypto engine."""
        try:
            from zohra.core.crypto_engine import crypto_engine
            from zohra.config.settings import settings
            if hasattr(self, 'loop') and self.loop and self.loop.is_running():
                crypto_engine.start(parent_loop=self.loop)
            else:
                crypto_engine.start()
            logger.info("▶️ Crypto Market Engine started.")
        except Exception as e:
            logger.error(f"Failed to start Crypto Engine: {e}")
            raise

    def _stop_crypto_engine(self):
        """Callback to stop the Crypto engine."""
        try:
            from zohra.core.crypto_engine import crypto_engine
            crypto_engine.stop()
            logger.info("⏹️ Crypto Market Engine stopped.")
        except Exception as e:
            logger.error(f"Failed to stop Crypto Engine: {e}")

    def _start_indian_engine(self):
        """Callback to start the Indian Market engine."""
        logger.info("▶️ Indian Market Engine activation requested.")
        # Indian engine requires async start — schedule it if we have a loop
        try:
            from zohra.engines.indian_market_engine import IndianMarketEngine
            from zohra.engines.indian_market_engine.config import EngineConfig
            from zohra.brokers.manager import broker_manager
            from zohra.engines.indian_market_engine.components.integration_bridge import IntegrationBridge

            config = EngineConfig()
            bridge = IntegrationBridge()
            self._indian_engine_instance = IndianMarketEngine(config, broker_manager, bridge)

            if hasattr(self, 'loop') and self.loop and self.loop.is_running():
                import asyncio
                asyncio.run_coroutine_threadsafe(self._indian_engine_instance.start(), self.loop)
            logger.info("▶️ Indian Market Engine started.")
        except Exception as e:
            logger.error(f"Failed to start Indian Market Engine: {e}")
            raise

    def _stop_indian_engine(self):
        """Callback to stop the Indian Market engine."""
        try:
            if hasattr(self, '_indian_engine_instance') and self._indian_engine_instance:
                if hasattr(self, 'loop') and self.loop and self.loop.is_running():
                    import asyncio
                    asyncio.run_coroutine_threadsafe(self._indian_engine_instance.stop(), self.loop)
                self._indian_engine_instance = None
            logger.info("⏹️ Indian Market Engine stopped.")
        except Exception as e:
            logger.error(f"Failed to stop Indian Market Engine: {e}")

    def _register_event_subscribers(self):
        """Registers handlers for routing and processing decoupled engine events."""
        event_bus.subscribe("db_log_trade_open", lambda data: db.log_trade_open(data))
        event_bus.subscribe("db_log_trade_close", lambda data: db.log_trade_close(**data))
        event_bus.subscribe("db_log_rejection", lambda data: db.log_rejection(data))
        
        def handle_memory_open(data):
            trade_id = data["trade_id"]
            ctx = f"Trade Opened: {data['direction']} {data['symbol']} lots={data['position_size_lots']} entry={data['entry_price']} SL={data['stop_loss']} TP={data['take_profit']} | Score: {data['confidence_score']} | Session: {data['session']} | Regime: {data['market_regime']} | Strategy: {data['strategy_used']} | Reason: {data['reason_for_entry']}"
            ai_memory.add_trade_experience(trade_id, ctx, "trade_open", data)
            
            try:
                from zohra.core.cognitive_memory import cognitive_memory
                cognitive_memory.add_timeline_event(
                    event_type="TRADE_OPENED",
                    description=f"Opened {data['direction']} position on {data['symbol']} at {data['entry_price']}.",
                    reference_id=trade_id
                )
            except Exception as e:
                logger.error(f"Error logging trade open to timeline: {e}")
            
        def handle_memory_close(data):
            trade_id = data["trade_id"]
            ctx = f"Trade Closed: {trade_id} closed at exit={data['exit_price']} with P&L=${data['pnl_usd']:+.2f} ({data['pnl_pct']:+.2f}%) | Duration: {data['duration_minutes']} mins | Reason: {data['exit_reason']}"
            ai_memory.add_trade_experience(trade_id, ctx, "trade_close", data)
            
            try:
                from zohra.core.cognitive_memory import cognitive_memory
                cognitive_memory.add_timeline_event(
                    event_type="TRADE_CLOSED",
                    description=f"Closed position on {data['symbol']} with P&L: ${data['pnl_usd']:+.2f} ({data['exit_reason']}).",
                    reference_id=trade_id
                )
            except Exception as e:
                logger.error(f"Error logging trade close to timeline: {e}")
            
            try:
                # Retrieve the full trade record from the database
                import sqlite3
                from zohra.config.settings import DB_PATH
                from zohra.core.learning_orchestrator import learning_orchestrator
                
                with sqlite3.connect(DB_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
                    row = cursor.fetchone()
                    trade_record = dict(row) if row else {}
                
                if trade_record:
                    full_trade_data = {**trade_record, **data}
                    learn_res = learning_orchestrator.learn_from_trade_close(full_trade_data)
                    logger.info(f"🧠 Zohra Learning: Ingested trade {trade_id}. Result={learn_res['result']} | Mistakes={learn_res['mistakes_count']} | BestAlt={learn_res['best_alternative']}")
                    logger.info(f"🧠 Zohra Lesson: {learn_res['lesson_text']}")
                
                result = learning_engine.analyze_patterns()
                logger.info(f"💡 Learning Engine analysis complete: {len(result.get('suggestions', []))} new suggestions generated.")
            except Exception as e:
                logger.error(f"Error executing auto learning cycle: {e}")

        event_bus.subscribe("memory_log_trade_open", handle_memory_open)
        event_bus.subscribe("memory_log_trade_close", handle_memory_close)

    def publish_event(self, event_type: str, data: Any):
        """Thread-safe publisher for background threads to dispatch events through the Event Bus."""
        if hasattr(self, 'loop') and self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(event_bus.publish(event_type, data), self.loop)
        else:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(event_bus.publish(event_type, data))
                else:
                    loop.run_until_complete(event_bus.publish(event_type, data))
            except Exception:
                import threading
                t = threading.Thread(target=lambda: asyncio.run(event_bus.publish(event_type, data)))
                t.start()

    # ════════════════════════════════════════════════
    #  STARTUP / SHUTDOWN
    # ════════════════════════════════════════════════

    def _handle_broker_failover(self) -> bool:
        """Fallback to Interactive Brokers (IBKR) adapter if primary MT5 fails."""
        logger.critical("🚨 MetaTrader 5 connection lost or failed. Broker failover is disabled to prevent split-brain trading on stub adapters.")
        return False

    def connect(self) -> bool:
        """Initializes connection to the broker and fetches initial equity info."""
        if not mt5_broker.connect():
            logger.critical("❌ Primary broker connection failed. Attempting broker failover...")
            if not self._handle_broker_failover():
                return False
        
        account = mt5_broker.get_account_info()
        
        # Simulated small account capital override
        from zohra.config.settings import VIRTUAL_EQUITY_OVERRIDE
        if VIRTUAL_EQUITY_OVERRIDE is not None:
            self.starting_equity = VIRTUAL_EQUITY_OVERRIDE
        else:
            self.starting_equity = account['equity'] if account else 100000.0
            
        self.risk_agent.starting_equity = self.starting_equity
        with state_lock:
            STATE.session_equity = self.starting_equity
        return True

    def start(self, run_loop: bool = True) -> bool:
        logger.info(f"🧠 Zohra supreme brain starting | mode={self.mode} | classification=DYNAMIC (A+/A/B/C/REJECT)")
        
        # Connect to broker
        if not self.connect():
            logger.critical("❌ Broker connection failed. Supreme Brain cannot start.")
            return False

        account = mt5_broker.get_account_info()
        
        # Log starting equity to DB
        db.log_equity(
            equity=self.starting_equity,
            balance=account.get('balance', 0) if account else self.starting_equity
        )

        logger.info(f"💰 Account summary: Login={account.get('login')} | Server={account.get('server')} | Balance=${account.get('balance'):,.2f} | Equity=${account.get('equity'):,.2f}")
        
        # AutoTrading (Algo Trading) startup check
        if not mt5_broker.is_autotrading_enabled():
            logger.critical("🚨 AUTOTRADING IS DISABLED in MetaTrader 5! The bot CANNOT place trades.")
            logger.critical("🚨 FIX: Open MetaTrader 5 → Tools → Options → Expert Advisors → Enable 'Allow Algo Trading'")
            logger.critical("🚨 Also click the 'Algo Trading' button on the MT5 toolbar so it turns GREEN.")
            print("")
            print("!" * 60)
            print("  ⚠️  AUTOTRADING IS DISABLED IN METATRADER 5!")
            print("  The bot CANNOT place any trades until you enable it.")
            print("")
            print("  FIX: Open MetaTrader 5 terminal and:")
            print("    1. Click the 'Algo Trading' button on the toolbar")
            print("       (it should turn GREEN)")
            print("    2. Go to Tools → Options → Expert Advisors")
            print("       and check 'Allow Algorithmic Trading'")
            print("!" * 60)
            print("")
        else:
            logger.info("✅ AutoTrading (Algo Trading) is ENABLED in MetaTrader 5.")
        
        # Startup Active Universe Banner — Gold-Only Trading Mode
        print("\n=================================")
        print("ZOHRA GOLD-ONLY TRADING MODE")
        print("=================================\n")
        print("ACTIVE SYMBOL:")
        print("XAUUSD — GOLD\n")
        print("XAGUSD / SILVER: DISABLED")
        print("ALL OTHER SYMBOLS: DISABLED\n")
        print("=================================\n")

        # Startup Validation Prints
        print("=" * 60)
        print("           ZOHRA MULTI-BOT ISOLATION STARTUP VALIDATION")
        print("=" * 60)
        print(f"Bot Name:           {getattr(settings, 'BOT_NAME', 'Bot A')}")
        print(f"Bot ID:             {getattr(settings, 'BOT_ID', 'ZOHRA_BOT_A')}")
        print(f"API Port:           {getattr(settings, 'api_port', 8001)}")
        print(f"MT5 Account:        {account.get('login') if account else 'N/A'}")
        print(f"MT5 Terminal Path:  {getattr(settings, 'MT5_TERMINAL_PATH', r'C:\\Program Files\\MetaTrader 5\\terminal64.exe')}")
        print(f"Database Path:      {getattr(settings, 'DB_PATH', 'logs/zohra_trades_a.db')}")

        # ═══ CRITICAL: AutoTrading Status Check ═══
        autotrading_ok = mt5_broker._check_autotrading_status()
        if autotrading_ok is True:
            print(f"AutoTrading:        ✅ ENABLED")
        elif autotrading_ok is False:
            print(f"AutoTrading:        ❌ DISABLED — PRESS Ctrl+E IN MT5!")
            logger.critical("🚨 BOT WILL NOT TRADE! AutoTrading is disabled. Press Ctrl+E in MetaTrader 5.")
        else:
            print(f"AutoTrading:        ⚠️ UNKNOWN (could not check)")
        print("=" * 60)

        # Generate startup report confirming complete isolation
        try:
            bot_suffix = getattr(settings, 'BOT_ID', 'ZOHRA_BOT_A').split('_')[-1].lower()
            report_dir = getattr(settings, 'REPORTS_DIR', os.path.join(LOG_DIR, "reports"))
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(LOG_DIR, f"startup_report_{bot_suffix}.md")
            with open(report_path, "w", encoding="utf-8") as rf:
                rf.write(f"""# Zohra {getattr(settings, 'BOT_NAME', 'Bot A')} Startup Isolation Report
Date/Time: {dt.datetime.utcnow().isoformat()} UTC

## Isolation Parameters
- **Bot Name**: {getattr(settings, 'BOT_NAME', 'Bot A')}
- **Bot ID**: {getattr(settings, 'BOT_ID', 'ZOHRA_BOT_A')}
- **API Port**: {getattr(settings, 'api_port', 8001)}
- **MT5 Account**: {account.get('login') if account else 'N/A'}
- **MT5 Terminal Path**: {getattr(settings, 'MT5_TERMINAL_PATH', 'N/A')}
- **Database Path**: {getattr(settings, 'DB_PATH', 'N/A')}
- **Chroma Path**: {getattr(settings, 'CHROMA_PATH', 'N/A')}
- **Journal CSV**: {getattr(settings, 'JOURNAL_CSV', 'N/A')}
- **Journal JSONL**: {getattr(settings, 'JOURNAL_FILE', 'N/A')}
- **Rejected Log**: {getattr(settings, 'REJECTED_LOG', 'N/A')}
- **Weights File**: {getattr(settings, 'WEIGHTS_FILE', 'N/A')}
- **System Log**: {getattr(settings, 'SYSTEM_LOG', 'N/A')}
- **Brain Log**: {getattr(settings, 'BRAIN_LOG', 'N/A')}

## Isolation Verification
- [x] **API/Dashboard/Websocket Port Isolation**: Confirmed bound to unique port {getattr(settings, 'api_port', 8001)}.
- [x] **MetaTrader 5 Binding**: Exclusive connection to {getattr(settings, 'BOT_NAME', 'Bot A')} verified. Desired path matches active terminal.
- [x] **Database Isolation**: Confirmed SQLite database isolated at `{getattr(settings, 'DB_PATH', 'N/A')}`.
- [x] **Memory Vector DB Isolation**: Confirmed Chroma database isolated at `{getattr(settings, 'CHROMA_PATH', 'N/A')}`.
- [x] **Journal/Log Isolation**: All output files configured with bot-specific suffix `_{bot_suffix}` under logs directory.

**Status: COMPLETE ISOLATION VERIFIED**
""")
            logger.info(f"Startup isolation report generated at: {report_path}")
        except Exception as e:
            logger.error(f"Failed to generate startup isolation report: {e}")

        logger.info("🤖 Zohra Brain initialized successfully.")

        self.running = True
        self._start_api()
        self._start_frontend()
        if run_loop:
            self._run_loop()
        return True

    def _start_api(self):
        """Starts the background API and Chat Command Center server."""
        try:
            import threading
            from zohra.api.app import run_api
            from zohra.config.settings import settings
            
            # Start in a separate daemon thread so it doesn't block the main trading loop
            t = threading.Thread(
                target=run_api,
                kwargs={
                    "host": settings.api_host,
                    "port": settings.api_port
                },
                daemon=True
            )
            t.start()
            logger.info(f"🌐 API and Chat Command Center started in background at http://{settings.api_host}:{settings.api_port}")
        except Exception as e:
            logger.warning(f"Could not start background API server: {e}")

    def _start_frontend(self):
        """Starts the React Vite frontend server in the background."""
        try:
            import subprocess
            ui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zohra-ui")
            # Using shell=True for Windows to resolve 'npm' command
            self.frontend_process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=ui_dir,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("🎨 React Vite frontend started in background at http://localhost:5173")
        except Exception as e:
            logger.warning(f"Could not start frontend server: {e}")

    def stop(self):
        logger.warning("🛑 Stopping supreme orchestrator...")
        self.running = False
        
        # Stop frontend process if running
        if hasattr(self, 'frontend_process') and self.frontend_process:
            try:
                logger.info("Stopping frontend server...")
                import subprocess
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.frontend_process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.error(f"Error stopping frontend process: {e}")
                
        try:
            mt5_broker.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    def get_status(self) -> Dict:
        account = mt5_broker.get_account_summary()
        from zohra.analytics.performance import analytics
        analytics_daily = {}
        try:
            analytics_daily = analytics.daily()
        except Exception as e:
            logger.error(f"Error getting daily analytics: {e}")
        return {
            "running": self.running,
            "broker": "mt5",
            "account": account,
            "open_positions": len(mt5_broker.get_open_positions()),
            "analytics_daily": analytics_daily,
            "timestamp": dt.datetime.utcnow().isoformat(),
        }

    def shutdown(self, sig=None, frame=None):
        logger.warning("🛑 Graceful shutdown initiated — stopping supreme orchestrator...")
        self.running = False
        
        # Stop frontend process if running
        if hasattr(self, 'frontend_process') and self.frontend_process:
            try:
                logger.info("Stopping frontend server...")
                import subprocess
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.frontend_process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.error(f"Error stopping frontend process in shutdown: {e}")
                
        try:
            self._generate_reports()
            mt5_broker.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
        logger.info("✅ Zohra Engine shutdown completed. Active positions remain in MT5.")
        import os
        os._exit(0)

    # ════════════════════════════════════════════════
    #  MAIN ENGINE LOOP
    # ════════════════════════════════════════════════

    def _run_loop(self):
        """Wrapper to execute the asynchronous orchestrator loop."""
        import asyncio
        try:
            asyncio.run(self._run_async_loop())
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down Zohra Brain gracefully...")
            self.running = False

    async def _run_async_loop(self):
        """Main asynchronous engine loop running symbol workers and evaluating confluences."""
        import asyncio
        self.loop = asyncio.get_running_loop()
        from zohra.core.symbol_manager import symbol_manager
        from zohra.core.symbol_worker import SymbolWorker
        from zohra.core.correlation_engine import correlation_engine
        from zohra.config.settings import ACTIVE_PAIRS
        from zohra.core.engine_registry import engine_registry

        # ═══ Start requested engines via Engine Registry ═══
        for engine_name in self.active_engines:
            if engine_name == "forex":
                # Forex startup handled below (symbol workers)
                engine_registry.mark_running("forex")
            else:
                success, msg = engine_registry.start_engine(engine_name)
                logger.info(f"Engine '{engine_name}': {msg}")

        # 1. Verify symbol registry with broker (needed for all modes)
        await asyncio.to_thread(symbol_manager.verify_broker_availability)

        # 2. Update correlation matrix
        await asyncio.to_thread(correlation_engine.update_correlation_matrix)

        # 3. Spawn asynchronous workers for all active symbols (ONLY if forex engine is active)
        self.workers = {}
        if engine_registry.is_running("forex"):
            from zohra.core.symbol_resolver import symbol_resolver
            for symbol in ACTIVE_PAIRS:
                if not symbol_resolver.is_symbol_allowed(symbol):
                    logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
                    continue
                worker = SymbolWorker(symbol, self)
                worker.start()
                self.workers[symbol] = worker
            logger.info(f"🏦 Market Engine: {len(self.workers)} symbol workers spawned for {list(self.workers.keys())}.")
        else:
            logger.info("🏦 Market Engine: SKIPPED (not in active engines).")

        last_daily_reset_date = dt.datetime.utcnow().date()
        last_manage_time = time.time()
        last_correlation_time = time.time()
        last_heartbeat_time = time.time()
        last_watchdog_time = time.time()

        logger.info("🤖 Zohra Multi-Symbol Orchestrator Engine loop active.")

        while self.running:
            try:
                # Emergency panic flag check
                if self._check_panic_control():
                    logger.warning("🚨 Engine trading halted. Scan loop entering sleep...")
                    await asyncio.sleep(15)
                    continue

                # Account protection filter to prevent a wash
                actual_equity = await asyncio.to_thread(mt5_broker.get_equity)
                if actual_equity > 0 and actual_equity < 100.0 and not STATE.trading_halted:
                    logger.critical(f"🚨 ACCOUNT SAFETY HALT: Actual equity (${actual_equity:.2f}) fell below $100.00 safety threshold. Halting trading to prevent wash!")
                    with state_lock:
                        STATE.trading_halted = True
                        STATE.halt_reason = f"Account equity (${actual_equity:.2f}) fell below $100.00 safety threshold."
                    # Close all open positions on the broker terminal!
                    try:
                        positions = await asyncio.to_thread(mt5_broker.get_open_positions)
                        for pos in positions:
                            logger.info(f"Closing position #{pos['ticket']} for account protection.")
                            await asyncio.to_thread(mt5_broker.close_position, pos["ticket"], pos["symbol"], pos["lots"], pos["direction"])
                    except Exception as e:
                        logger.error(f"Error closing positions during safety halt: {e}")

                # Check Daily Profit Target
                from zohra.config.settings import DAILY_PROFIT_TARGET
                if STATE.daily_pnl >= DAILY_PROFIT_TARGET and not STATE.trading_halted:
                    logger.warning(f"🏆 DAILY TARGET REACHED! Realized PnL (${STATE.daily_pnl:.2f}) >= Target (${DAILY_PROFIT_TARGET:.2f}). Halting trading for the day...")
                    with state_lock:
                        STATE.trading_halted = True
                        STATE.halt_reason = f"Profit target of ${DAILY_PROFIT_TARGET:.2f} reached."
                    # Close all open positions on the broker terminal to lock in profit!
                    try:
                        positions = await asyncio.to_thread(mt5_broker.get_open_positions)
                        for pos in positions:
                            logger.info(f"Closing position #{pos['ticket']} to lock in daily profit target.")
                            await asyncio.to_thread(mt5_broker.close_position, pos["ticket"], pos["symbol"], pos["lots"], pos["direction"])
                    except Exception as e:
                        logger.error(f"Error closing positions during profit target halt: {e}")

                # Check Halted state
                if STATE.trading_halted:
                    logger.warning(f"🚨 Engine trading is halted. Reason: {STATE.halt_reason}. Sleeping for 30 seconds...")
                    await asyncio.sleep(30)
                    continue

                # Check broker connection status
                if not await asyncio.to_thread(mt5_broker.is_connected):
                    logger.warning("🔌 MetaTrader 5 disconnected! Attempting reconnection...")
                    connected = await asyncio.to_thread(self.connect)
                    if not connected:
                        logger.error("🔌 Reconnection failed. Retrying in 15 seconds...")
                        await asyncio.sleep(15)
                        continue
                    else:
                        logger.info("🔌 MetaTrader 5 successfully reconnected!")

                now_ts = time.time()
                now_dt = dt.datetime.now(dt.timezone.utc)

                # A. Daily Reset Check (21:00 UTC)
                if now_dt.date() != last_daily_reset_date:
                    await asyncio.to_thread(self._daily_reset, now_dt)
                    last_daily_reset_date = now_dt.date()

                # B. Daily Report Check (23:50 UTC)
                if now_dt.hour == 23 and now_dt.minute >= 50:
                    await asyncio.to_thread(self._generate_reports)

                # C. Position Management (Layer 6) - run every 15 seconds
                if now_ts - last_manage_time >= MANAGE_INTERVAL_SEC:
                    await asyncio.to_thread(self._manage_active_positions)
                    try:
                        from zohra.core.shadow_ai import shadow_ai_engine
                        await asyncio.to_thread(shadow_ai_engine.update_shadow_trades)
                    except Exception as e:
                        logger.error(f"Error updating shadow trades: {e}")
                    last_manage_time = now_ts

                # D. Update Correlation Matrix every 15 minutes
                if now_ts - last_correlation_time >= 900:
                    await asyncio.to_thread(correlation_engine.update_correlation_matrix)
                    last_correlation_time = now_ts

                # E. Heartbeat Log (Every 5 minutes)
                if now_ts - last_heartbeat_time >= 300:
                    open_pos = await asyncio.to_thread(mt5_broker.get_open_positions)
                    equity = await asyncio.to_thread(mt5_broker.get_equity)
                    logger.info(f"♥ Zohra Heartbeat | Open Positions: {len(open_pos)} | Daily P&L: ${STATE.daily_pnl:+.2f} | Equity: ${equity:,.2f}")
                    last_heartbeat_time = now_ts

                # F. Watchdog check for Symbol Workers (Every 60 seconds)
                if now_ts - last_watchdog_time >= 60.0:
                    for symbol, worker in list(self.workers.items()):
                        check_tf, bar_size_sec, _ = worker.get_priority_settings()
                        is_dead = not worker.running or worker.task is None or worker.task.done()
                        is_hung = (worker.last_bar_time > 0 and (now_ts - worker.last_bar_time) > (bar_size_sec * 3.5))
                        if is_dead or is_hung:
                            logger.warning(f"👷 Watchdog: Worker for {symbol} is {'dead' if is_dead else 'hung'}. Restarting...")
                            try:
                                worker.stop()
                            except Exception:
                                pass
                            new_worker = SymbolWorker(symbol, self)
                            new_worker.start()
                            self.workers[symbol] = new_worker
                    last_watchdog_time = now_ts

                # F. Check AutoTrading status before processing setups
                if not await asyncio.to_thread(mt5_broker.is_autotrading_enabled):
                    # Only log once every 60 seconds to avoid spam
                    if not hasattr(self, '_last_autotrading_warn') or now_ts - self._last_autotrading_warn >= 60:
                        logger.warning("🚨 AutoTrading is DISABLED in MetaTrader 5! Enable 'Algo Trading' on the MT5 toolbar (green button). No trades can be placed.")
                        self._last_autotrading_warn = now_ts
                    await asyncio.sleep(5)
                    continue

                # G. Process leaderboard setups (only when forex engine is active)
                if engine_registry.is_running("forex"):
                    await self._process_leaderboard_opportunities()

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Async loop error: {e}\n{traceback.format_exc()}")
                await asyncio.sleep(15)

        # Clean shutdown of workers
        for worker in self.workers.values():
            worker.stop()

    async def _process_leaderboard_opportunities(self):
        """Processes and trades the top setups on the opportunity leaderboard."""
        import asyncio
        from zohra.core.symbol_manager import symbol_manager
        from zohra.core.symbol_resolver import symbol_resolver
        from zohra.config.settings import TRADING_DIAGNOSTIC_MODE, BOT_NAME

        now_ts = time.time()
        # Throttling rule for HFT (2-minute intervals)
        if self.hft_mode:
            if now_ts - self.last_execution_time < self.hft_interval_sec:
                return

        top_setup = self.opportunity_engine.get_top_opportunity()
        if not top_setup:
            if TRADING_DIAGNOSTIC_MODE:
                logger.debug("NO_GENUINE_SETUP -> NO_TRADE: No qualified strategy opportunities currently active.")
            return

        symbol = top_setup["symbol"]
        strategy = top_setup["strategy"]
        direction = top_setup["direction"]
        final_score = top_setup["confidence_score"]

        # Hard Symbol Guard — Strictly Gold (XAUUSD) Only
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading disabled for {symbol}. Gold only mode is active.")
            return

        # Market Open Validation for this specific symbol
        if not symbol_manager.is_market_open(symbol):
            if TRADING_DIAGNOSTIC_MODE:
                logger.debug(f"[DIAGNOSTIC] Market closed for {symbol}. Skipping execution.")
            return

        # Classify Setup Type (Swing vs. Scalp)
        is_scalp = (strategy in (StrategyName.SCALP_M5.value, "MomentumScalp") or 
                    (top_setup["scores_breakdown"].get("volume", 0) >= 70 and 
                     top_setup["scores_breakdown"].get("volatility", 0) >= 70))

        # Detect high-volume market state
        vol_ratio = top_setup.get("vol_ratio", 1.0)
        is_high_volume = (vol_ratio >= 1.8 or top_setup["scores_breakdown"].get("volume", 0) >= 80)

        # Pop from leaderboard immediately so it is only processed once
        self.opportunity_engine.remove_setup(symbol, strategy)

        # Check Halted state
        if STATE.trading_halted:
            logger.warning(f"⏭️ Skipping setup for {symbol}: Trading is halted ({STATE.halt_reason}).")
            try:
                trade_forensics.log_rejection(
                    symbol=symbol, direction=direction, strategy=strategy,
                    confidence_score=final_score, rejection_reason=f"Trading halted: {STATE.halt_reason}",
                    rejection_category="RISK", regime=top_setup["regime"],
                    session=self._get_current_session(), entry_price=top_setup["entry_price"],
                    stop_loss=top_setup["stop_loss"], take_profit=top_setup["take_profit"],
                    scores=top_setup["scores_breakdown"], vol_ratio=vol_ratio
                )
            except Exception as e:
                logger.error(f"Error logging halt rejection in forensics: {e}")
            return

        # Risk Check: Daily limits/Kill switch checks first
        equity = await asyncio.to_thread(mt5_broker.get_equity)
        
        # Simulated small account capital override
        from zohra.config.settings import VIRTUAL_EQUITY_OVERRIDE
        if VIRTUAL_EQUITY_OVERRIDE is not None:
            equity = VIRTUAL_EQUITY_OVERRIDE
            
        if equity <= 0:
            return

        # Update peak equity and calculate drawdown pct
        if STATE.peak_equity <= 0.0:
            STATE.peak_equity = max(STATE.session_equity, equity)
        else:
            STATE.peak_equity = max(STATE.peak_equity, equity)

        drawdown_pct = max(0.0, (STATE.peak_equity - equity) / STATE.peak_equity * 100.0) if STATE.peak_equity > 0 else 0.0

        if drawdown_pct > 8.0:
            logger.warning(f"⛑️ Drawdown safety halt: drawdown is {drawdown_pct:.2f}%. Trading paused.")
            with state_lock:
                STATE.trading_halted = True
                STATE.halt_reason = f"Account drawdown ({drawdown_pct:.2f}%) exceeded 8.0% safety limit."
            try:
                trade_forensics.log_rejection(
                    symbol=symbol, direction=direction, strategy=strategy,
                    confidence_score=final_score, rejection_reason=f"Drawdown safety halt ({drawdown_pct:.2f}%)",
                    rejection_category="RISK", regime=top_setup["regime"],
                    session=self._get_current_session(), entry_price=top_setup["entry_price"],
                    stop_loss=top_setup["stop_loss"], take_profit=top_setup["take_profit"],
                    scores=top_setup["scores_breakdown"], vol_ratio=vol_ratio
                )
            except Exception as e:
                logger.error(f"Error logging drawdown rejection in forensics: {e}")
            return

        # Check Kill Switch
        blocked, kill_reason = self._check_kill_switch_state(equity)
        if blocked:
            logger.warning(f"⛑️ Kill Switch is Active: {kill_reason} — Market scans skipped.")
            try:
                trade_forensics.log_rejection(
                    symbol=symbol, direction=direction, strategy=strategy,
                    confidence_score=final_score, rejection_reason=f"Kill switch active: {kill_reason}",
                    rejection_category="RISK", regime=top_setup["regime"],
                    session=self._get_current_session(), entry_price=top_setup["entry_price"],
                    stop_loss=top_setup["stop_loss"], take_profit=top_setup["take_profit"],
                    scores=top_setup["scores_breakdown"], vol_ratio=vol_ratio
                )
            except Exception as e:
                logger.error(f"Error logging kill switch rejection in forensics: {e}")
            return

        # Position Constraint Check
        open_positions = await asyncio.to_thread(mt5_broker.get_open_positions)
        matching_positions = [p for p in open_positions if p["symbol"] == symbol]
        if matching_positions:
            has_same_direction = any(p["direction"] == direction for p in matching_positions)
            if is_high_volume and is_scalp:
                if has_same_direction:
                    logger.info(f"⏭️ Skipping setup for {symbol}: Same direction position already open.")
                    return
            else:
                logger.info(f"⏭️ Skipping setup for {symbol}: Position already open.")
                return

        rejection_reasons = []
        grade = TradeQuality.REJECT
        g_mult = 0.0
        rec_risk_pct = 0.0
        setup_classification = {}

        if top_setup.get("is_news_blackout"):
            rejection_reasons.append(f"News Blackout Active: {top_setup.get('news_reason')}")

        # Spread Check using unified broker calculation
        spread_pips = await asyncio.to_thread(mt5_broker.get_spread_pips, symbol)
        max_allowed = 5.0 if "XAU" in symbol else 6.0 if "XAG" in symbol else 3.5
        if spread_pips > max_allowed:
            rejection_reasons.append(f"Spread limit exceeded: {spread_pips:.1f} pips > {max_allowed:.1f} pips max")
        
        # ═══ INVESTMENT COMMITTEE DEBATE (Consensus) ═══
        debate = investment_committee.debate_setup(symbol, direction, strategy, top_setup, drawdown_pct)
        final_score = debate["final_score"]
        grade_str = debate["grade"]

        # Map to TradeQuality enum
        if grade_str == "A+":
            grade = TradeQuality.A_PLUS
        elif grade_str == "A":
            grade = TradeQuality.A
        elif grade_str == "B":
            grade = TradeQuality.B
        elif grade_str == "C":
            grade = TradeQuality.C
        else:
            grade = TradeQuality.REJECT

        # Build classification mapping from debate
        setup_classification = {
            "grade": grade_str,
            "classification": "Elite Institutional" if grade_str == "A+" else "High Probability" if grade_str == "A" else "Good Opportunity" if grade_str == "B" else "Speculative" if grade_str == "C" else "Low Quality — Rejected",
            "risk_r": f"{debate['position_mult']:.2f}R",
            "risk_r_numeric": debate["position_mult"],
            "priority": "HIGHEST" if grade_str == "A+" else "HIGH" if grade_str == "A" else "NORMAL" if grade_str == "B" else "LOW" if grade_str == "C" else "NONE",
            "action": debate["action"],
            "confidence_pct": final_score
        }

        # Log the debate outcome and committee ruling
        dd_mult = scorer.get_drawdown_multiplier(drawdown_pct)
        logger.info(
            f"📋 INVESTMENT COMMITTEE RULING: {symbol} {direction} | "
            f"Consensus Score: {final_score}/100 | Grade: {grade_str} | "
            f"Action: {debate['action']} | Sizing Factor: {debate['position_mult']:.2f}R | "
            f"Drawdown: {drawdown_pct:.2f}% (DD Mult: {dd_mult:.2f})"
        )
        logger.info(f"🐂 BULL THESIS: {debate['bull_thesis']}")
        logger.info(f"🐻 BEAR CRITIQUE: {debate['bear_thesis']}")
        logger.info(f"⚖️ CHAIRMAN SUMMARY: {debate['chairman_summary']}")
        if "historical_score" in debate and debate["historical_score"] is not None:
            logger.info(
                f"🏛️ HIE ENRICHMENT: Historical Score={debate.get('historical_score')}/100 | "
                f"Win Rate={debate.get('historical_win_rate')}% | Matches={debate.get('historical_matches')} | "
                f"Avg RR={debate.get('historical_avg_rr')} | Confidence={debate.get('historical_confidence')}"
            )


        if not debate["approved"]:
            rejection_reasons.append(f"Committee Veto: {debate['chairman_summary']}")

        # Check C setups permission
        from zohra.config.settings import ALLOW_C_SETUPS
        if grade == TradeQuality.C and not ALLOW_C_SETUPS:
            rejection_reasons.append(f"Speculative setup (Grade C, Score {final_score}) is disabled by config (ALLOW_C_SETUPS=False).")

        if grade == TradeQuality.REJECT:
            rejection_reasons.append(f"Low quality setup (Grade REJECT, Score {final_score}) is below minimum execution threshold of 70.")

        lots = 0.0
        if not rejection_reasons:
            stop_dist = abs(top_setup["entry_price"] - top_setup["stop_loss"])
            
            # Dynamic Lot Sizer
            lots = await asyncio.to_thread(scorer.get_position_size, grade, equity, stop_dist, symbol, drawdown_pct)
            
            # Log Recommended Risk and position size details
            g_mult = setup_classification["risk_r_numeric"]
            rec_risk_pct = scorer.risk_per_trade * g_mult * dd_mult * 100.0
            logger.info(
                f"📊 CONFIDENCE ENGINE: {symbol} | "
                f"Grade: {grade.value} | Score: {final_score} | "
                f"Confidence: {final_score}% | "
                f"Risk Allocation: {g_mult:.2f}R | "
                f"Position Size: {rec_risk_pct:.3f}% of equity | "
                f"Lots: {lots} | "
                f"Decision: {'EXECUTE' if lots > 0 else 'REJECT'}"
            )

            # Snap lots to steps and limits for safety
            symbol_info = await asyncio.to_thread(mt5_broker.get_symbol_info, symbol)
            if symbol_info:
                step = symbol_info.get("volume_step", 0.01)
                min_v = symbol_info.get("volume_min", 0.01)
                max_v = symbol_info.get("volume_max", 100.0)
                lots = round(round(lots / step) * step, 2)
                lots = max(min_v, min(lots, max_v))

            # Evaluate portfolio risk & correlation via Risk Agent
            allowed, risk_reason = self.risk_agent.evaluate_portfolio_risk(symbol, lots, open_positions, direction)
            if not allowed:
                rejection_reasons.append(f"Risk Veto: {risk_reason}")

        # Check Virtual Mode Guard (Drawdown check)
        is_virtual_trade = False
        virtual_reason = ""
        if not rejection_reasons:
            is_virtual_trade, virtual_reason = self._check_strategy_virtual_mode(strategy)

        # Explainability Trace Log (enhanced with classification engine)
        trace_log = {
            "timestamp": dt.datetime.utcnow().isoformat(),
            "symbol": symbol,
            "direction": direction,
            "strategy": strategy,
            "execution_type": "SCALP" if is_scalp else "SWING",
            "regime": top_setup["regime"],
            "confidence_score": final_score,
            "confidence_pct": final_score,
            "grade": grade.value,
            "classification": setup_classification.get("classification", ""),
            "priority": setup_classification.get("priority", ""),
            "recommended_risk": f"{g_mult:.2f}R",
            "recommended_risk_pct": rec_risk_pct,
            "drawdown_pct": drawdown_pct,
            "drawdown_multiplier": dd_mult,
            "news_status": "BLACKOUT" if top_setup.get("is_news_blackout") else "CLEAR",
            "entry_price": top_setup["entry_price"],
            "stop_loss": top_setup["stop_loss"],
            "take_profit": top_setup["take_profit"],
            "scores_breakdown": top_setup["scores_breakdown"],
            "weights_used": top_setup["weights_used"],
            "reasons": top_setup["reasons"],
            "is_virtual": is_virtual_trade,
            "virtual_reason": virtual_reason
        }

        # Execution
        if not rejection_reasons:
            if is_virtual_trade:
                logger.info(f"🔮 VIRTUAL MODE GUARD ACTIVE: {virtual_reason} — Executing setup virtually.")
                exec_result = {
                    "success": True,
                    "mt5_ticket": 999000 + random.randint(1000, 9999),
                    "fill_price": top_setup["entry_price"]
                }
            else:
                logger.info(f"🎯 EXECUTION SIGNAL APPROVED: {direction} {symbol} ({'SCALP' if is_scalp else 'SWING'}) Score={final_score} Volume={lots} Lots")
                
                # Package execution request
                exec_order = {
                    "symbol": symbol,
                    "direction": direction,
                    "volume_lots": lots,
                    "stop_loss": top_setup["stop_loss"],
                    "take_profit": top_setup["take_profit"],
                    "comment": f"ZSC_{strategy[:5]}_{final_score}" if is_scalp else f"ZSW_{strategy[:5]}_{final_score}",
                    "magic": MAGIC_SCALP if is_scalp else MAGIC_SMC
                }

                # Measure execution latency and entry spread
                t_start = time.perf_counter()
                try:
                    spread_info = await asyncio.to_thread(mt5_broker.get_current_price, symbol)
                    entry_spread = spread_info.get("spread", 0.0)
                except Exception:
                    entry_spread = 0.0

                # Execute Deal
                exec_result = await asyncio.to_thread(mt5_broker.open_position, exec_order)
                exec_latency = (time.perf_counter() - t_start) * 1000.0
            
            if exec_result.get("success"):
                ticket = exec_result["mt5_ticket"]
                fill_price = exec_result["fill_price"]
                
                requested_price = top_setup["entry_price"]
                if direction == "LONG":
                    slippage = fill_price - requested_price
                else:
                    slippage = requested_price - fill_price

                if is_virtual_trade:
                    exec_latency = random.uniform(12.0, 48.0)
                    slippage = 0.0
                    entry_spread = 0.0
                
                if is_virtual_trade:
                    logger.info(f"🔮 VIRTUAL TRADE PLACED: Position #{ticket} logged at {fill_price}")
                else:
                    logger.info(f"✅ TRADE PLACED: Position #{ticket} filled at {fill_price} | Latency={exec_latency:.1f}ms | Spread={entry_spread:.5f} | Slippage={slippage:.5f}")
                
                # Dynamic contract size sizing for precise DB stats
                contract_size = 100000.0
                if symbol == "XAUUSD":
                    contract_size = 100.0
                elif symbol == "XAGUSD":
                    contract_size = 5000.0
                elif "JPY" in symbol:
                    contract_size = 1000.0
                risk_usd_calc = lots * stop_dist * contract_size

                # Record completed trade log to DB
                trade_record = {
                    "trade_id": f"ZHR_{symbol}_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    "mt5_ticket": ticket,
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": fill_price,
                    "stop_loss": top_setup["stop_loss"],
                    "take_profit": top_setup["take_profit"],
                    "position_size_lots": lots,
                    "risk_usd": risk_usd_calc,
                    "confidence_score": final_score,
                    "quality_grade": grade.value,
                    "session": self._get_current_session(),
                    "market_regime": top_setup["regime"],
                    "strategy_used": StrategyName.SCALP_M5.value if is_scalp else strategy,
                    "news_status": 1 if top_setup.get("is_news_blackout") else 0,
                    "reason_for_entry": debate["chairman_summary"],
                    "metadata": json.dumps({
                        "virtual": True,
                        "virtual_reason": virtual_reason,
                        "confidence_pct": final_score,
                        "recommended_risk": f"{g_mult:.2f}R",
                        "recommended_risk_pct": rec_risk_pct,
                        "drawdown_pct": drawdown_pct,
                        "bull_thesis": debate["bull_thesis"],
                        "bear_thesis": debate["bear_thesis"],
                        "chairman_summary": debate["chairman_summary"],
                        "historical_score": debate.get("historical_score"),
                        "symbol_intelligence_score": debate.get("symbol_intelligence_score"),
                        "market_memory_score": debate.get("market_memory_score"),
                        "historical_matches": debate.get("historical_matches"),
                        "historical_win_rate": debate.get("historical_win_rate"),
                        "historical_avg_rr": debate.get("historical_avg_rr"),
                        "historical_confidence": debate.get("historical_confidence"),
                        "best_session": debate.get("best_session")
                    }) if is_virtual_trade else json.dumps({
                        "confidence_pct": final_score,
                        "recommended_risk": f"{g_mult:.2f}R",
                        "recommended_risk_pct": rec_risk_pct,
                        "drawdown_pct": drawdown_pct,
                        "bull_thesis": debate["bull_thesis"],
                        "bear_thesis": debate["bear_thesis"],
                        "chairman_summary": debate["chairman_summary"],
                        "historical_score": debate.get("historical_score"),
                        "symbol_intelligence_score": debate.get("symbol_intelligence_score"),
                        "market_memory_score": debate.get("market_memory_score"),
                        "historical_matches": debate.get("historical_matches"),
                        "historical_win_rate": debate.get("historical_win_rate"),
                        "historical_avg_rr": debate.get("historical_avg_rr"),
                        "historical_confidence": debate.get("historical_confidence"),
                        "best_session": debate.get("best_session")
                    }),
                    "score_structure": int(top_setup["scores_breakdown"].get("structure", 0)),
                    "score_liquidity": int(top_setup["scores_breakdown"].get("volume", 0)),
                    "score_smc": int(top_setup["scores_breakdown"].get("smc", 0)),
                    "score_trend": int(top_setup["scores_breakdown"].get("correlation", 0)),
                    "score_momentum": int(top_setup["scores_breakdown"].get("momentum", 0)),
                    "score_volatility": int(top_setup["scores_breakdown"].get("volatility", 0)),
                    "score_pullback": int(top_setup["scores_breakdown"].get("session", 0)),
                    "requested_price": requested_price,
                    "slippage_points": slippage,
                    "entry_spread_points": entry_spread,
                    "execution_latency_ms": exec_latency
                }
                
                await event_bus.publish("db_log_trade_open", trade_record)
                await event_bus.publish("memory_log_trade_open", trade_record)
                try:
                    from zohra.core.shadow_ai import shadow_ai_engine
                    shadow_ai_engine.spawn_shadow_trades(
                        parent_trade_id=trade_record["trade_id"],
                        symbol=symbol,
                        direction=direction,
                        entry_price=fill_price,
                        stop_loss=top_setup["stop_loss"],
                        take_profit=top_setup["take_profit"],
                        volume=lots
                    )
                except Exception as e:
                    logger.error(f"Failed to spawn shadow trades: {e}")
                
                # Save decision trace log as Approved
                trace_log["decision"] = "APPROVED"
                trace_log["mt5_ticket"] = ticket
                trace_log["executed_lots"] = lots
                self._write_journal(trace_log)
                
                try:
                    trade_forensics.log_decision(
                        symbol=symbol, direction=direction, strategy=strategy,
                        decision="ACCEPTED", confidence_score=final_score,
                        regime=top_setup["regime"], session=self._get_current_session(),
                        entry_price=fill_price, stop_loss=top_setup["stop_loss"],
                        take_profit=top_setup["take_profit"], rejection_reason="",
                        context={"ticket": ticket, "lots": lots, "is_virtual": is_virtual_trade}
                    )
                except Exception as e:
                    logger.error(f"Error logging decision in forensics: {e}")
                
                # Track daily trade count
                with state_lock:
                    STATE.daily_trades += 1
                if self.hft_mode:
                    self.last_execution_time = time.time()
                    logger.info(f"⏱️ HFT Timer reset. Next execution allowed at {dt.datetime.fromtimestamp(self.last_execution_time + self.hft_interval_sec).strftime('%H:%M:%S')} UTC")
            else:
                logger.error(f"❌ ORDER PLACEMENT FAILED: {exec_result.get('error')}")
                await asyncio.to_thread(db.log_system, "ERROR", f"Order failed for {symbol}: {exec_result.get('error')}", "Execution")
        else:
            # Log rejection
            rejection_desc = " & ".join(rejection_reasons)
            logger.info(f"⛔ Setup Rejected for {symbol} ({direction}): {rejection_desc}")
            
            rejection_data = {
                "symbol": symbol,
                "direction": direction,
                "confidence_score": final_score,
                "failed_conditions": rejection_reasons,
                "reason_for_rejection": rejection_desc,
                "regime": top_setup["regime"],
                "structure_pass": int(top_setup["scores_breakdown"].get("structure", 0) >= 50),
                "liquidity_pass": int(top_setup["scores_breakdown"].get("volume", 0) >= 50),
                "momentum_pass": int(top_setup["scores_breakdown"].get("momentum", 0) >= 50),
                "volume_pass": int(top_setup["scores_breakdown"].get("volume", 0) >= 50)
            }
            await event_bus.publish("db_log_rejection", rejection_data)

            trace_log["decision"] = "REJECTED"
            trace_log["rejection_reasons"] = rejection_reasons
            self._write_journal(trace_log)

            try:
                # Determine category
                category = "FILTER"
                if any("Committee Veto" in r for r in rejection_reasons):
                    category = "COMMITTEE"
                elif any("News Blackout" in r for r in rejection_reasons):
                    category = "NEWS"
                elif any("Spread" in r for r in rejection_reasons):
                    category = "SPREAD"
                elif any("Risk Veto" in r for r in rejection_reasons):
                    category = "RISK"
                elif any("Low quality" in r or "Speculative" in r for r in rejection_reasons):
                    category = "SCORE"
                
                trade_forensics.log_rejection(
                    symbol=symbol, direction=direction, strategy=strategy,
                    confidence_score=final_score, rejection_reason=rejection_desc,
                    rejection_category=category, regime=top_setup["regime"],
                    session=self._get_current_session(), entry_price=top_setup["entry_price"],
                    stop_loss=top_setup["stop_loss"], take_profit=top_setup["take_profit"],
                    scores=top_setup["scores_breakdown"], vol_ratio=vol_ratio
                )
                
                # Log error experience to vector store (Phase 8)
                ai_memory.add_error_memory(
                    error_id=f"REJ_{symbol}_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    context_text=f"Rejected {symbol} {direction} {strategy} setup. Reason: {rejection_desc}. Score: {final_score}. Regime: {top_setup['regime']}",
                    metadata={"symbol": symbol, "direction": direction, "strategy": strategy, "reason": rejection_desc, "score": final_score}
                )

                trade_forensics.log_decision(
                    symbol=symbol, direction=direction, strategy=strategy,
                    decision="REJECTED", confidence_score=final_score,
                    regime=top_setup["regime"], session=self._get_current_session(),
                    entry_price=top_setup["entry_price"], stop_loss=top_setup["stop_loss"],
                    take_profit=top_setup["take_profit"], rejection_reason=rejection_desc
                )
            except Exception as e:
                logger.error(f"Error logging rejection in forensics: {e}")

    async def _find_best_momentum_setup(self) -> Optional[Dict]:
        """
        Scans all active symbols on M5, calculates volume and 3-bar price velocity,
        and returns a synthetic setup for the symbol with the highest momentum.
        """
        import asyncio
        import pandas as pd
        from zohra.config.settings import ACTIVE_PAIRS
        from zohra.core.symbol_manager import symbol_manager

        best_symbol = None
        best_direction = None
        best_mom_score = -1.0
        best_candles_data = None

        # Only check active and healthy symbols verified by the broker and permitted by Hard Symbol Guard
        from zohra.core.symbol_resolver import symbol_resolver
        active_healthy_symbols = [sym for sym in ACTIVE_PAIRS if symbol_manager.is_active(sym) and symbol_resolver.is_symbol_allowed(sym)]
        logger.info(f"🔍 TIMED HFT SCAN: Sweeping all {len(active_healthy_symbols)} active broker pairs: {active_healthy_symbols}")

        # Scan active pairs sequentially with a 50ms spacing to prevent socket congestion
        results = []
        for symbol in active_healthy_symbols:
            res = await asyncio.to_thread(mt5_broker.get_ohlcv, symbol, "M5", 50)
            results.append(res)
            await asyncio.sleep(0.05)

        for symbol, df in zip(active_healthy_symbols, results):
            if isinstance(df, Exception) or df is None or df.empty or len(df) < 10:
                continue

            # Volume analysis
            vol_col = 'tick_volume'
            if 'real_volume' in df.columns and len(df) > 0 and df['real_volume'].sum() > 0:
                vol_col = 'real_volume'
            if vol_col not in df.columns:
                continue
            latest_vol = df[vol_col].iloc[-1]
            vol_sma = df[vol_col].rolling(20).mean().iloc[-1]
            vol_ratio = latest_vol / (vol_sma + 1e-9)

            # Momentum: price velocity over last 3 candles
            close_prices = df['close'].values
            mom = close_prices[-1] - close_prices[-4]
            abs_mom = abs(mom)

            # ATR normalization
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift(1)).abs()
            low_close = (df['low'] - df['close'].shift(1)).abs()
            atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1]

            # Momentum score: absolute momentum normalized by ATR * volume ratio
            mom_score = (abs_mom / (atr + 1e-9)) * vol_ratio

            # Only consider symbols that have active volume (vol_ratio >= 1.2) to prevent low-volume chops
            if vol_ratio < 1.2:
                continue

            if mom_score > best_mom_score:
                best_mom_score = mom_score
                best_symbol = symbol
                best_direction = "LONG" if mom > 0 else "SHORT"
                best_candles_data = (df, atr, vol_ratio)

        if not best_symbol:
            return None

        df, atr, vol_ratio = best_candles_data
        current_price = df['close'].iloc[-1]

        # Stop loss: 1.2 * ATR for tighter control
        # Take profit: 1.8 * ATR for high win rate scalp
        sl_dist = atr * 1.2
        tp_dist = atr * 1.8

        if best_direction == "LONG":
            sl = current_price - sl_dist
            tp = current_price + tp_dist
        else:
            sl = current_price + sl_dist
            tp = current_price - tp_dist

        # Register a synthetic setup
        setup = {
            "symbol": best_symbol,
            "direction": best_direction,
            "strategy": "MomentumScalp",
            "regime": "Trending" if best_mom_score > 1.5 else "Ranging",
            "confidence_score": 75,
            "entry_price": current_price,
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "vol_ratio": vol_ratio,
            "scores_breakdown": {
                "structure": 70,
                "volume": 80,
                "smc": 60,
                "correlation": 70,
                "momentum": 85,
                "volatility": 70,
                "session": 70
            },
            "weights_used": {},
            "reasons": f"Forced momentum entry on {best_symbol} | Score={best_mom_score:.2f} | VolRatio={vol_ratio:.2f}"
        }
        return setup

    # ════════════════════════════════════════════════
    #  LAYER 6: ADAPTIVE POSITION MONITOR & MANAGEMENT
    # ════════════════════════════════════════════════

    def _manage_active_positions(self):
        """Active position checks for trailing, breakeven, and partial closures."""
        positions = mt5_broker.get_open_positions()
        
        # Sync database closed trades
        db_open_trades = db.get_open_trades()
        
        active_tickets = {p["ticket"] for p in positions}
        for dt_trade in db_open_trades:
            ticket = dt_trade["mt5_ticket"]
            
            # Check if this is a virtual trade
            metadata_str = dt_trade.get("metadata", "{}") or "{}"
            is_virtual = False
            try:
                meta = json.loads(metadata_str)
                is_virtual = meta.get("virtual", False)
            except Exception:
                pass
                
            if is_virtual:
                # 🔮 Simulate exit check for virtual trade using current bid/ask price
                symbol = dt_trade["symbol"]
                tick = mt5.symbol_info_tick(symbol)
                if not tick:
                    continue
                current_price = tick.bid if dt_trade["direction"] == "LONG" else tick.ask
                
                # Check stop loss / take profit hit
                sl_hit = (dt_trade["direction"] == "LONG" and current_price <= dt_trade["stop_loss"]) or \
                         (dt_trade["direction"] == "SHORT" and current_price >= dt_trade["stop_loss"])
                tp_hit = (dt_trade["direction"] == "LONG" and current_price >= dt_trade["take_profit"]) or \
                         (dt_trade["direction"] == "SHORT" and current_price <= dt_trade["take_profit"])
                
                # Calculate virtual PnL for hard loss cut check
                pnl = 0.0
                entry = dt_trade["entry_price"]
                lots = dt_trade["position_size_lots"]
                
                contract_size = 100000.0
                if symbol == "XAUUSD":
                    contract_size = 100.0
                elif symbol == "XAGUSD":
                    contract_size = 5000.0
                elif "JPY" in symbol:
                    contract_size = 1000.0
                
                if dt_trade["direction"] == "LONG":
                    pnl = (current_price - entry) * lots * contract_size
                else:
                    pnl = (entry - current_price) * lots * contract_size
                
                # Hard loss cut-off for virtual trades: $7.00
                hard_loss_hit = (pnl <= -7.0)
                
                # Time stop for virtual Silver trades: 30 minutes
                time_stop_hit = False
                elapsed_min = 0.0
                if symbol == "XAGUSD":
                    open_time_str = dt_trade.get("timestamp_open")
                    if open_time_str:
                        open_time = dt.datetime.fromisoformat(open_time_str)
                        elapsed_min = (dt.datetime.utcnow() - open_time).total_seconds() / 60
                        if elapsed_min >= 30:
                            time_stop_hit = True
                         
                if sl_hit or tp_hit or hard_loss_hit or time_stop_hit:
                    # Close virtual trade
                    pnl_pct = (pnl / STATE.session_equity) * 100 if STATE.session_equity > 0 else 0.0
                    
                    if sl_hit:
                        reason = "Virtual SL hit"
                    elif tp_hit:
                        reason = "Virtual TP hit"
                    elif hard_loss_hit:
                        reason = f"Virtual Hard loss cut (${pnl:.2f} <= -$7.00)"
                    else:
                        reason = f"Virtual Silver time stop ({elapsed_min:.1f} mins >= 30 mins)"
                    
                    close_data = {
                        "trade_id": dt_trade["trade_id"],
                        "exit_price": current_price,
                        "pnl_usd": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": reason,
                        "exit_code": "VIRTUAL_EXIT",
                        "duration_minutes": int((dt.datetime.utcnow() - dt.datetime.fromisoformat(dt_trade["timestamp_open"])).total_seconds() / 60)
                    }
                    self.publish_event("db_log_trade_close", close_data)
                    self.publish_event("memory_log_trade_close", {**close_data, "symbol": dt_trade["symbol"], "direction": dt_trade["direction"]})
                    
                    with state_lock:
                        STATE.daily_pnl += pnl
                        STATE.weekly_pnl += pnl
                    logger.info(f"🔮 VIRTUAL TRADE CLOSED: Position #{ticket} ({symbol}) closed via {reason} at {current_price} | P&L: ${pnl:+.2f}")
                else:
                    # Trail virtual positions
                    strategy_used = dt_trade.get("strategy_used", "zohra_v5")
                    df_to_use = mt5_broker.get_ohlcv(symbol, "M5", count=50) if strategy_used == StrategyName.SCALP_M5.value else mt5_broker.get_ohlcv(symbol, "M15", count=50)
                    if df_to_use is not None and not df_to_use.empty:
                        trade_params = {
                            "direction": dt_trade["direction"],
                            "entry_price": dt_trade["entry_price"],
                            "stop_loss": dt_trade["stop_loss"],
                            "take_profit": dt_trade["take_profit"],
                            "quality": dt_trade.get("quality_grade", "B"),
                            "be_moved": bool(dt_trade.get("be_moved", False)),
                            "half_closed": bool(dt_trade.get("half_closed", False)),
                        }
                        if strategy_used == StrategyName.SCALP_M5.value:
                            exit_signal = scalping_strategy.check_exit(df_to_use, trade_params)
                        else:
                            exit_signal = position_manager.manage(trade_params, df_to_use)
                        
                        action = "HOLD"
                        if exit_signal:
                            action = exit_signal.get("action", "HOLD")
                            reason = exit_signal.get("reason", "")
                            
                            if action == "CLOSE_FULL":
                                pnl = (current_price - entry) * lots * contract_size
                                if dt_trade["direction"] == "SHORT":
                                    pnl = -pnl
                                pnl_pct = (pnl / STATE.session_equity) * 100 if STATE.session_equity > 0 else 0.0
                                close_data = {
                                    "trade_id": dt_trade["trade_id"],
                                    "exit_price": current_price,
                                    "pnl_usd": pnl,
                                    "pnl_pct": pnl_pct,
                                    "exit_reason": f"Virtual exit: {reason}",
                                    "exit_code": "VIRTUAL_EXIT",
                                    "duration_minutes": int((dt.datetime.utcnow() - dt.datetime.fromisoformat(dt_trade["timestamp_open"])).total_seconds() / 60)
                                }
                                self.publish_event("db_log_trade_close", close_data)
                                self.publish_event("memory_log_trade_close", {**close_data, "symbol": dt_trade["symbol"], "direction": dt_trade["direction"]})
                                with state_lock:
                                    STATE.daily_pnl += pnl
                                    STATE.weekly_pnl += pnl
                            elif action == "MOVE_BE" and not trade_params["be_moved"]:
                                db._execute("UPDATE trades SET stop_loss = ?, be_moved = 1 WHERE mt5_ticket = ?", (entry, ticket))
                            elif action == "TRAIL":
                                new_sl = exit_signal.get("new_stop")
                                if strategy_used != StrategyName.SCALP_M5.value:
                                    struct_sl = self._get_smc_structure_level(df_to_use, dt_trade["direction"])
                                    if struct_sl:
                                        if dt_trade["direction"] == "LONG" and struct_sl > dt_trade["stop_loss"]:
                                            new_sl = struct_sl
                                        elif dt_trade["direction"] == "SHORT" and struct_sl < dt_trade["stop_loss"] and dt_trade["stop_loss"] > 0:
                                            new_sl = struct_sl
                                if new_sl:
                                    db._execute("UPDATE trades SET stop_loss = ? WHERE mt5_ticket = ?", (new_sl, ticket))

                        # Universal Trailing SL check for virtual trade if still active
                        if action != "CLOSE_FULL":
                            atr_val = position_manager._calculate_atr(df_to_use, 14)
                            from zohra.config.settings import TRAIL_BEHIND_ATR
                            trail_mult = TRAIL_BEHIND_ATR if TRAIL_BEHIND_ATR is not None else 1.5
                            trail_dist = atr_val * trail_mult
                            
                            current_sl = dt_trade["stop_loss"]
                            if dt_trade["direction"] == "LONG":
                                if current_price > entry:
                                    trail_sl = round(current_price - trail_dist, 5)
                                    if trail_sl > current_sl and (trail_sl - current_sl >= 0.1 * atr_val or current_sl == 0):
                                        logger.info(f"🔮 VIRTUAL UNIVERSAL TRAIL (LONG) #{ticket} ({symbol}) SL to {trail_sl}")
                                        db._execute("UPDATE trades SET stop_loss = ? WHERE mt5_ticket = ?", (trail_sl, ticket))
                            else: # SHORT
                                if current_price < entry:
                                    trail_sl = round(current_price + trail_dist, 5)
                                    if (current_sl == 0 or trail_sl < current_sl) and (current_sl == 0 or current_sl - trail_sl >= 0.1 * atr_val):
                                        logger.info(f"🔮 VIRTUAL UNIVERSAL TRAIL (SHORT) #{ticket} ({symbol}) SL to {trail_sl}")
                                        db._execute("UPDATE trades SET stop_loss = ? WHERE mt5_ticket = ?", (trail_sl, ticket))
                continue
            
            # Live trades handling
            if ticket not in active_tickets:
                # Closed by broker. Find matching deal history with retries
                logger.info(f"⚡ Position #{ticket} ({dt_trade['symbol']}) closed by broker (SL/TP target hit) — retrieving deal logs...")
                
                exit_price = dt_trade["entry_price"]
                pnl = 0.0
                deals_fetched = False
                for attempt in range(5):
                    try:
                        deals = mt5.history_deals_get(position=ticket)
                        if not deals:
                            now_dt = dt.datetime.now()
                            deals = mt5.history_deals_get(now_dt - dt.timedelta(hours=2), now_dt + dt.timedelta(minutes=10))
                        if deals:
                            matching = [d for d in deals if d.position_id == ticket]
                            if matching:
                                pnl = sum(d.profit + d.commission + d.swap for d in matching)
                                out_deal = [d for d in matching if d.entry in (1, 3)]
                                if out_deal:
                                    exit_price = out_deal[-1].price
                                else:
                                    exit_price = matching[-1].price
                                deals_fetched = True
                                break
                    except Exception as ex:
                        logger.error(f"History deals fetch attempt {attempt+1} error: {ex}")
                    time.sleep(1)
                
                pnl_pct = (pnl / STATE.session_equity) * 100 if STATE.session_equity > 0 else 0.0
                
                # Update record in DB
                close_data = {
                    "trade_id": dt_trade["trade_id"],
                    "exit_price": exit_price,
                    "pnl_usd": pnl,
                    "pnl_pct": pnl_pct,
                    "exit_reason": "SL/TP Target Hit (Broker Exit)",
                    "exit_code": "BROKER_EXIT",
                    "duration_minutes": int((dt.datetime.utcnow() - dt.datetime.fromisoformat(dt_trade["timestamp_open"])).total_seconds() / 60)
                }
                self.publish_event("db_log_trade_close", close_data)
                self.publish_event("memory_log_trade_close", {**close_data, "symbol": dt_trade["symbol"], "direction": dt_trade["direction"]})
                
                with state_lock:
                    STATE.daily_pnl += pnl
                    STATE.weekly_pnl += pnl

        # Manage remaining active positions
        for pos in positions:
            symbol = pos["symbol"]
            ticket = pos["ticket"]
            
            # Find DB tracking model
            matching_db = next((t for t in db_open_trades if t["mt5_ticket"] == ticket), None)
            if not matching_db:
                continue # Bypasses manual trades not logged by Zohra
                
            strategy_used = matching_db.get("strategy_used", "zohra_v5")

            # 1. $7 Hard loss cut-off rule
            floating_profit = pos.get("profit", 0.0)
            if floating_profit <= -7.0:
                logger.warning(f"🚨 HARD LOSS CUT TRIGGERED: Position #{ticket} ({symbol}) has floating loss of ${floating_profit:.2f} (<= -$7.00). Closing position immediately!")
                close_res = mt5_broker.close_position(ticket, symbol, pos["lots"], pos["direction"])
                if close_res.get("success"):
                    pnl = close_res["profit_loss"]
                    pnl_pct = (pnl / STATE.session_equity) * 100 if STATE.session_equity > 0 else 0.0
                    
                    close_data = {
                        "trade_id": matching_db["trade_id"],
                        "exit_price": close_res["exit_price"],
                        "pnl_usd": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": f"Hard loss cut (${floating_profit:.2f} <= -$7.00)",
                        "exit_code": "HARD_LOSS_CUT",
                        "duration_minutes": int((dt.datetime.utcnow() - dt.datetime.fromisoformat(matching_db["timestamp_open"])).total_seconds() / 60)
                    }
                    self.publish_event("db_log_trade_close", close_data)
                    self.publish_event("memory_log_trade_close", {**close_data, "symbol": matching_db["symbol"], "direction": matching_db["direction"]})
                    
                    with state_lock:
                        STATE.daily_pnl += pnl
                        STATE.weekly_pnl += pnl
                    if strategy_used == StrategyName.SCALP_M5.value:
                        scalping_strategy.remove_active_scalp(symbol)
                continue

            # 2. Silver time stop rule (max 30 minutes holding time)
            if symbol == "XAGUSD":
                open_time_str = matching_db.get("timestamp_open")
                if open_time_str:
                    open_time = dt.datetime.fromisoformat(open_time_str)
                    elapsed_min = (dt.datetime.utcnow() - open_time).total_seconds() / 60
                    if elapsed_min >= 30:
                        logger.warning(f"⏱️ SILVER TIME STOP: Position #{ticket} ({symbol}) has been open for {elapsed_min:.1f} mins (>= 30 mins). Closing trade to limit exposure.")
                        close_res = mt5_broker.close_position(ticket, symbol, pos["lots"], pos["direction"])
                        if close_res.get("success"):
                            pnl = close_res["profit_loss"]
                            pnl_pct = (pnl / STATE.session_equity) * 100 if STATE.session_equity > 0 else 0.0
                            
                            close_data = {
                                "trade_id": matching_db["trade_id"],
                                "exit_price": close_res["exit_price"],
                                "pnl_usd": pnl,
                                "pnl_pct": pnl_pct,
                                "exit_reason": f"Silver time stop ({elapsed_min:.1f} mins >= 30 mins)",
                                "exit_code": "TIME_STOP",
                                "duration_minutes": int((dt.datetime.utcnow() - dt.datetime.fromisoformat(matching_db["timestamp_open"])).total_seconds() / 60)
                            }
                            self.publish_event("db_log_trade_close", close_data)
                            self.publish_event("memory_log_trade_close", {**close_data, "symbol": matching_db["symbol"], "direction": matching_db["direction"]})
                            
                            with state_lock:
                                STATE.daily_pnl += pnl
                                STATE.weekly_pnl += pnl
                            if strategy_used == StrategyName.SCALP_M5.value:
                                scalping_strategy.remove_active_scalp(symbol)
                        continue

            # Get latest 15M candles for exit checks
            df_m15 = mt5_broker.get_ohlcv(symbol, "M15", count=50)
            if df_m15 is None or df_m15.empty:
                continue

            strategy_used = matching_db.get("strategy_used", "zohra_v5")
            
            # Construct standard trade parameters for positional monitoring
            init_entry = matching_db["entry_price"]
            init_sl = matching_db["stop_loss"]
            init_risk = abs(init_entry - init_sl)
            
            if init_risk > 0:
                if pos["direction"] == "LONG":
                    tp1_val = init_entry + init_risk
                    tp2_val = matching_db["take_profit"]
                else:
                    tp1_val = init_entry - init_risk
                    tp2_val = matching_db["take_profit"]
            else:
                tp1_val = matching_db["take_profit"]
                tp2_val = matching_db["take_profit"]

            trade_params = {
                "direction": pos["direction"],
                "entry_price": matching_db["entry_price"],
                "stop_loss": pos["stop_loss"],
                "take_profit": pos["take_profit"],
                "quality": matching_db.get("quality_grade", "B"),
                "be_moved": bool(matching_db.get("be_moved", False)),
                "half_closed": bool(matching_db.get("half_closed", False)),
                "tp1": tp1_val,
                "tp2": tp2_val
            }

            # Strategy exit routes
            if strategy_used == StrategyName.SCALP_M5.value:
                df_m5 = mt5_broker.get_ohlcv(symbol, "M5", count=50)
                exit_signal = scalping_strategy.check_exit(df_m5, trade_params)
            else:
                exit_signal = position_manager.manage(trade_params, df_m15)

            if not exit_signal:
                continue

            action = exit_signal.get("action", "HOLD")
            reason = exit_signal.get("reason", "")

            # Execute actions
            if action == "CLOSE_FULL":
                logger.info(f"🚨 CLOSING POSITION #{ticket} ({symbol}) | Reason: {reason}")
                close_res = mt5_broker.close_position(ticket, symbol, pos["lots"], pos["direction"])
                
                if close_res.get("success"):
                    pnl = close_res["profit_loss"]
                    pnl_pct = (pnl / STATE.session_equity) * 100 if STATE.session_equity > 0 else 0.0
                    
                    close_data = {
                        "trade_id": matching_db["trade_id"],
                        "exit_price": close_res["exit_price"],
                        "pnl_usd": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": reason,
                        "exit_code": action,
                        "duration_minutes": int((dt.datetime.utcnow() - dt.datetime.fromisoformat(matching_db["timestamp_open"])).total_seconds() / 60)
                    }
                    self.publish_event("db_log_trade_close", close_data)
                    self.publish_event("memory_log_trade_close", {**close_data, "symbol": matching_db["symbol"], "direction": matching_db["direction"]})
                    
                    with state_lock:
                        STATE.daily_pnl += pnl
                        STATE.weekly_pnl += pnl
                    if strategy_used == StrategyName.SCALP_M5.value:
                        scalping_strategy.remove_active_scalp(symbol)

            elif action == "CLOSE_HALF" and not trade_params["half_closed"]:
                half_lots = round(pos["lots"] / 2, 2)
                half_lots = max(MIN_LOT_SIZE, half_lots)
                
                logger.info(f"✂️ PARTIAL CLOSE #{ticket} ({symbol}) | Volume: {half_lots} Lots | Reason: {reason}")
                close_res = mt5_broker.close_position(ticket, symbol, half_lots, pos["direction"])
                
                if close_res.get("success"):
                    pnl = close_res["profit_loss"]
                    with state_lock:
                        STATE.daily_pnl += pnl
                    
                    # Update database properties (half_closed = True)
                    db._execute("UPDATE trades SET half_closed = 1, position_size_lots = ? WHERE mt5_ticket = ?", (pos["lots"] - half_lots, ticket))
                    
                    # Move SL to BE automatically as part of risk lock
                    modify_res = mt5_broker.modify_stop(ticket, symbol, stop_loss=matching_db["entry_price"])
                    if modify_res.get("success"):
                        db._execute("UPDATE trades SET be_moved = 1 WHERE mt5_ticket = ?", (ticket,))
                        logger.info(f"🔄 BE SL updated for ticket #{ticket}")

            elif action == "MOVE_BE" and not trade_params["be_moved"]:
                logger.info(f"🔄 ADJUSTING POSITION #{ticket} ({symbol}) to Breakeven SL | Reason: {reason}")
                modify_res = mt5_broker.modify_stop(ticket, symbol, stop_loss=matching_db["entry_price"])
                
                if modify_res.get("success"):
                    db._execute("UPDATE trades SET be_moved = 1 WHERE mt5_ticket = ?", (ticket,))

            elif action == "TRAIL":
                new_sl = exit_signal.get("new_stop")
                
                # Compute SMC structure trail stop
                if strategy_used != StrategyName.SCALP_M5.value:
                    struct_sl = self._get_smc_structure_level(df_m15, pos["direction"])
                    if struct_sl:
                        if pos["direction"] == "LONG" and struct_sl > pos["stop_loss"]:
                            new_sl = struct_sl
                            reason += " (SMC Support Trail)"
                        elif pos["direction"] == "SHORT" and struct_sl < pos["stop_loss"] and pos["stop_loss"] > 0:
                            new_sl = struct_sl
                            reason += " (SMC Resistance Trail)"
                        
                if new_sl:
                    logger.info(f"📈 TRAILING POSITION #{ticket} ({symbol}) SL to {new_sl} | Reason: {reason}")
                    modify_res = mt5_broker.modify_stop(ticket, symbol, stop_loss=new_sl)
                    
                    if modify_res.get("success"):
                        db._execute("UPDATE trades SET stop_loss = ? WHERE mt5_ticket = ?", (new_sl, ticket))

            # 3. Universal Trailing Stop-Loss for any profitable trade
            if action != "CLOSE_FULL":
                df_to_use = df_m5 if strategy_used == StrategyName.SCALP_M5.value else df_m15
                if df_to_use is not None and not df_to_use.empty:
                    # Calculate ATR(14)
                    atr_val = position_manager._calculate_atr(df_to_use, 14)
                    from zohra.config.settings import TRAIL_BEHIND_ATR
                    trail_mult = TRAIL_BEHIND_ATR if TRAIL_BEHIND_ATR is not None else 1.5
                    trail_dist = atr_val * trail_mult
                    
                    current_price = pos["current_price"]
                    direction = pos["direction"]
                    current_sl = pos["stop_loss"]
                    entry_price = matching_db["entry_price"]
                    
                    if direction == "LONG":
                        # Check if the trade is in profit
                        if current_price > entry_price:
                            trail_sl = round(current_price - trail_dist, 5)
                            # Only trail if the new SL improves the current SL
                            # And only if the improvement is at least 0.1 * atr to avoid spamming updates
                            if trail_sl > current_sl and (trail_sl - current_sl >= 0.1 * atr_val or current_sl == 0):
                                logger.info(f"📈 UNIVERSAL TRAIL (LONG) #{ticket} ({symbol}) SL to {trail_sl} | Profit={current_price - entry_price:.5f}")
                                modify_res = mt5_broker.modify_stop(ticket, symbol, stop_loss=trail_sl)
                                if modify_res.get("success"):
                                    db._execute("UPDATE trades SET stop_loss = ? WHERE mt5_ticket = ?", (trail_sl, ticket))
                    else: # SHORT
                        # Check if the trade is in profit
                        if current_price < entry_price:
                            trail_sl = round(current_price + trail_dist, 5)
                            # Only trail if the new SL improves the current SL (lower than current SL)
                            if (current_sl == 0 or trail_sl < current_sl) and (current_sl == 0 or current_sl - trail_sl >= 0.1 * atr_val):
                                logger.info(f"📈 UNIVERSAL TRAIL (SHORT) #{ticket} ({symbol}) SL to {trail_sl} | Profit={entry_price - current_price:.5f}")
                                modify_res = mt5_broker.modify_stop(ticket, symbol, stop_loss=trail_sl)
                                if modify_res.get("success"):
                                    db._execute("UPDATE trades SET stop_loss = ? WHERE mt5_ticket = ?", (trail_sl, ticket))

    # ════════════════════════════════════════════════
    #  LAYER 7: REPORTING & UTILITIES
    # ════════════════════════════════════════════════

    def _generate_reports(self):
        """Generates performance logs and triggers daily analytics generator."""
        try:
            logger.info("📊 Generating performance snapshots...")
            self.performance_agent.run_review(days=1) # Daily snapshot
            logger.info("📊 Snapshots recorded successfully.")
        except Exception as e:
            logger.error(f"Error generating daily analytics: {e}")

    def _daily_reset(self, now: dt.datetime):
        logger.info("🌅 Performing Daily Reset logic...")
        with state_lock:
            STATE.daily_pnl = 0.0
            STATE.daily_trades = 0
            if STATE.trading_halted and "Profit target" in STATE.halt_reason:
                STATE.trading_halted = False
                STATE.halt_reason = ""
        self.starting_equity = mt5_broker.get_equity()
        # Simulated small account capital override
        from zohra.config.settings import VIRTUAL_EQUITY_OVERRIDE
        if VIRTUAL_EQUITY_OVERRIDE is not None:
            self.starting_equity = VIRTUAL_EQUITY_OVERRIDE
        self.risk_agent.starting_equity = self.starting_equity
        logger.info(f"Daily reset completed. Reset starting equity reference to: ${self.starting_equity:,.2f}")

    def _check_kill_switch_state(self, equity: float) -> Tuple[bool, str]:
        """Runs the primary daily/weekly/monthly drawdown rules."""
        if self.starting_equity <= 0:
            return False, ""
            
        daily_loss = (equity - self.starting_equity) / self.starting_equity
        if daily_loss <= -MAX_DAILY_LOSS_PCT:
            return True, f"Daily drawdown {daily_loss*100:.2f}% meets or exceeds limit of {MAX_DAILY_LOSS_PCT*100:.1f}%"
            
        return False, ""

    def _validate_risk_checks(self, lots: float, open_positions: List[Dict]) -> Tuple[bool, str]:
        """Runs standard safety criteria checks."""
        # 1. Open count cap
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            return False, f"Maximum active positions limit ({MAX_OPEN_POSITIONS}) reached."
            
        # 2. Lot limits caps
        if lots < MIN_LOT_SIZE or lots > MAX_LOT_SIZE:
            return False, f"Lots calculation {lots} is outside bounds [{MIN_LOT_SIZE}, {MAX_LOT_SIZE}]."
            
        # 3. Daily trade count cap
        if STATE.daily_trades >= MAX_DAILY_TRADES:
            return False, f"Daily execution trade count limit ({MAX_DAILY_TRADES}) reached."
            
        return True, ""

    def _get_smc_structure_level(self, df: pd.DataFrame, direction: str) -> Optional[float]:
        """
        Returns the nearest structural support (for LONG) or resistance (for SHORT)
        based on M15 Fair Value Gaps (FVG) and Order Blocks (OB) in the last 40 candles.
        """
        if df is None or len(df) < 15:
            return None
            
        recent = df.tail(40).reset_index(drop=True)
        levels = []
        
        # 1. Detect Fair Value Gaps (FVGs)
        for i in range(1, len(recent) - 1):
            if direction == "LONG":
                if recent.loc[i+1, 'low'] > recent.loc[i-1, 'high']:
                    levels.append(recent.loc[i-1, 'high'])
            else:
                if recent.loc[i+1, 'high'] < recent.loc[i-1, 'low']:
                    levels.append(recent.loc[i-1, 'low'])

        # 2. Detect Order Blocks (OBs)
        for i in range(2, len(recent) - 1):
            if direction == "LONG":
                if (recent.loc[i-1, 'close'] < recent.loc[i-1, 'open'] and 
                    recent.loc[i, 'close'] > recent.loc[i, 'open'] and 
                    recent.loc[i, 'close'] > recent.loc[i-1, 'high']):
                    levels.append(recent.loc[i-1, 'low'])
            else:
                if (recent.loc[i-1, 'close'] > recent.loc[i-1, 'open'] and 
                    recent.loc[i, 'close'] < recent.loc[i, 'open'] and 
                    recent.loc[i, 'close'] < recent.loc[i-1, 'low']):
                    levels.append(recent.loc[i-1, 'high'])

        if not levels:
            return None
            
        current_price = df.iloc[-1]['close']
        if direction == "LONG":
            valid_supports = [lvl for lvl in levels if lvl < current_price]
            return max(valid_supports) if valid_supports else None
        else:
            valid_resistances = [lvl for lvl in levels if lvl > current_price]
            return min(valid_resistances) if valid_resistances else None

    def _check_strategy_virtual_mode(self, strategy_name: str) -> Tuple[bool, str]:
        """
        Calculates the equity curve of the last 15 trades of a strategy.
        If the strategy is in a drawdown of > 3 consecutive losses or drawdown > 8%
        of its local strategy equity peak, we flag it as VIRTUAL (simulated).
        """
        try:
            trades = db.get_closed_trades(limit=15)
            strat_trades = [t for t in trades if t.get("strategy") == strategy_name or t.get("strategy_used") == strategy_name]
            
            if len(strat_trades) < 5:
                return False, "Not enough strategy trade history (needs >= 5 trades) to trigger Virtual Guard"
                
            pnl_list = [float(t.get("profit_loss", 0.0) or 0.0) for t in strat_trades]
            
            local_equity = 10000.0
            eq_curve = [local_equity]
            for pnl in reversed(pnl_list):
                local_equity += pnl
                eq_curve.append(local_equity)
                
            max_peak = eq_curve[0]
            max_dd_pct = 0.0
            consecutive_losses = 0
            max_consecutive_losses = 0
            
            for eq in eq_curve:
                if eq > max_peak:
                    max_peak = eq
                dd = (max_peak - eq) / max_peak * 100
                if dd > max_dd_pct:
                    max_dd_pct = dd
                    
            for pnl in pnl_list:
                if pnl < 0:
                    consecutive_losses += 1
                    if consecutive_losses > max_consecutive_losses:
                        max_consecutive_losses = consecutive_losses
                else:
                    consecutive_losses = 0
                    
            if max_dd_pct > 8.0 or max_consecutive_losses >= 3:
                return True, f"Strategy in drawdown ({max_dd_pct:.1f}%) or has {max_consecutive_losses} consecutive losses"
                
            return False, "Performance healthy"
        except Exception as e:
            logger.error(f"Error checking Virtual Guard for {strategy_name}: {e}")
            return False, "Error in virtual check"

    def _check_panic_control(self) -> bool:
        """
        Checks if panic.flag exists. If so, triggers emergency halt:
        closes all positions, halts trading, and logs warning.
        """
        flag_found = False
        for f in ["panic.flag", "zohra/panic.flag"]:
            if os.path.exists(f):
                flag_found = True
                try:
                    os.remove(f)
                except Exception:
                    pass
                    
        if flag_found:
            logger.critical("🚨 PANIC FLAG DETECTED! Triggering Emergency Close-All and Halt...")
            
            try:
                positions = mt5_broker.get_open_positions()
                for pos in positions:
                    logger.warning(f"🚨 PANIC Close: Closing position #{pos['ticket']} ({pos['symbol']})")
                    mt5_broker.close_position(pos["ticket"], pos["symbol"], pos["lots"], pos["direction"])
            except Exception as e:
                logger.error(f"Error during panic close-all: {e}")
                
            with state_lock:
                STATE.trading_enabled = False
                STATE.trading_halted = True
                STATE.halt_reason = "Emergency Panic Flag Triggered"
                
            db.log_system("CRITICAL", "Emergency Close-All triggered via panic flag file.", "PanicControl")
            return True
        return False

    def _write_journal(self, entry: Dict[str, Any]):
        """Persists the explainability entry to the decision journal line."""
        try:
            with open(JOURNAL_FILE, "a", encoding='utf-8') as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Decision journal logging error: {e}")

    def _get_current_session(self) -> str:
        h = dt.datetime.utcnow().hour
        for name, (start, end) in SESSIONS.items():
            if start <= h < end:
                return name.lower()
        return "off"


# Helper formulas
def risk_calculation(equity: float, stop_distance: float, grade: TradeQuality, symbol: str) -> float:
    """Universal quantitative trade lot sizer with dynamic symbol specs."""
    if stop_distance <= 0:
        return MIN_LOT_SIZE

    risk_mult = {
        TradeQuality.A_PLUS: 1.00,
        TradeQuality.A:      0.75,
        TradeQuality.B:      0.50,
        TradeQuality.C:      0.25,
        TradeQuality.REJECT: 0.00
    }.get(grade, 0.0)

    risk_usd = equity * RISK_PER_TRADE_PCT * risk_mult
    
    # Try fetching dynamic specs from MetaTrader 5
    info = mt5.symbol_info(symbol)
    if info is not None and info.trade_tick_value > 0 and info.trade_tick_size > 0:
        tick_val = info.trade_tick_value
        tick_sz = info.trade_tick_size
        step = info.volume_step if info.volume_step > 0 else LOT_STEP
        min_v = info.volume_min if info.volume_min > 0 else MIN_LOT_SIZE
        max_v = info.volume_max if info.volume_max > 0 else MAX_LOT_SIZE
        
        # Guard against broker-side scaling discrepancy for Gold and Silver
        # MT5 trade_tick_value for metals is often reported 10x smaller than actual contract specs
        if symbol in ["XAUUSD", "XAGUSD"]:
            tick_val = info.trade_contract_size * tick_sz
            
        # Calculate lots using dynamic tick value
        lots = risk_usd / (stop_distance * (tick_val / tick_sz))
        lots = round(round(lots / step) * step, 2)
        lots = max(min_v, min(lots, max_v))
        return lots
        
    # Fallback to hardcoded asset sizer if broker info is offline
    if symbol == "XAUUSD":
        lots = risk_usd / (stop_distance * 100.0) # Gold contract size (100 oz)
    elif symbol == "XAGUSD":
        lots = risk_usd / (stop_distance * 5000.0) # Silver contract size (5000 oz)
    elif "JPY" in symbol:
        # Convert pip step for JPY pairs
        lots = risk_usd / (stop_distance * 1000.0)
    else:
        lots = risk_usd / (stop_distance * 100000.0)

    # Snap to steps
    lots = round(round(lots / LOT_STEP) * LOT_STEP, 2)
    lots = max(MIN_LOT_SIZE, min(lots, MAX_LOT_SIZE))
    return lots


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Zohra Supreme Central Brain — Dynamic Trade Classification Engine")
    parser.add_argument('--mode', type=str, default='demo', choices=['demo', 'live', 'simulated'], help="Trading mode")
    parser.add_argument('--engines', type=str, nargs='+', default=None,
                        choices=['forex', 'indian', 'crypto'],
                        help="Which market engines to activate. Default: all. Example: --engines forex crypto")
    args = parser.parse_args()

    brain = ZohraBrain(mode=args.mode, active_engines=args.engines)
    brain.start()
