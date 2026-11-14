"""
╔══════════════════════════════════════════════════════════════════════╗
║   HIE ORCHESTRATOR                                                   ║
║   Manages startup sequencing of all HIE modules.                     ║
║   Designed to be started as a daemon thread from ZohraBrain.         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import threading
import time
import datetime as dt
from typing import Dict

logger = logging.getLogger("zohra.hie.orchestrator")


class HIEOrchestrator:
    """
    Orchestrates the startup and monitoring of all 12 HIE modules.
    Each module starts as a daemon thread that runs in the background.
    Failure of any module does NOT affect the main trading loop.
    """

    def __init__(self):
        self._started = False
        self._start_time: dt.datetime = None
        self._status: Dict = {
            "running": False,
            "modules": {},
            "started_at": None,
            "total_candles": 0,
            "total_setups": 0,
            "total_outcomes": 0,
            "total_patterns": 0,
            "total_profiles": 0,
            "failure_flags": 0
        }

    def start(self):
        """
        Start all HIE modules in dependency order.
        This is called from ZohraBrain.__init__ in a daemon thread.
        """
        if self._started:
            logger.info("HIE Orchestrator already started.")
            return

        logger.info("🚀 HIE Orchestrator: Starting Historical Intelligence Engine modules...")
        self._start_time = dt.datetime.utcnow()
        self._status["started_at"] = self._start_time.isoformat()
        self._status["running"] = True

        # ── Phase 1: Data Layer ──
        self._start_module("HistoricalDataEngine", self._start_data_engine)
        time.sleep(5)  # Allow initial connection before dependent modules start

        # ── Phase 2: Detection & Analysis (depends on data) ──
        self._start_module("SetupDetectionEngine", self._start_setup_detection)
        self._start_module("OutcomeAnalysisEngine", self._start_outcome_analysis)

        # ── Phase 3: Aggregation (depends on outcomes) ──
        time.sleep(2)
        self._start_module("HistoricalPatternDatabase", self._start_pattern_db)
        self._start_module("MarketMemoryEngine", self._start_memory)
        self._start_module("SymbolIntelligenceProfiles", self._start_symbol_profiles)

        # ── Phase 4: Intelligence Layers (depends on aggregations) ──
        time.sleep(2)
        self._start_module("FailurePatternDetector", self._start_failure_detector)
        self._start_module("ConfidenceCalibration", self._start_calibration)
        self._start_module("LearningEngineHIE", self._start_learning)
        self._start_module("StrategyValidationLab", self._start_validation_lab)
        self._start_module("EvolutionEngine", self._start_evolution_engine)

        # ── Phase 5: Quantitative Research Agents ──
        time.sleep(2)
        self._start_module("SMCResearchAgent", self._start_smc_research)
        self._start_module("TrendResearchAgent", self._start_trend_research)
        self._start_module("SessionResearchAgent", self._start_session_research)
        self._start_module("CorrelationResearchAgent", self._start_correlation_research)

        self._started = True
        logger.info("✅ HIE Orchestrator: All modules started successfully.")

        # Start status monitor
        t = threading.Thread(target=self._status_monitor_loop, daemon=True, name="HIE-StatusMonitor")
        t.start()

    def _start_module(self, name: str, fn):
        """Start a single module with error isolation."""
        try:
            t = threading.Thread(target=fn, daemon=True, name=f"HIE-Start-{name}")
            t.start()
            self._status["modules"][name] = "starting"
            logger.info(f"  ▶ {name} initialized.")
        except Exception as e:
            self._status["modules"][name] = f"error: {e}"
            logger.error(f"HIE: Failed to start {name}: {e}")

    def _start_data_engine(self):
        try:
            from zohra.hie.historical_data_engine import historical_data_engine
            historical_data_engine.start()
            self._status["modules"]["HistoricalDataEngine"] = "running"
        except Exception as e:
            self._status["modules"]["HistoricalDataEngine"] = f"error: {e}"

    def _start_setup_detection(self):
        try:
            from zohra.hie.setup_detection_engine import setup_detection_engine
            setup_detection_engine.start()
            self._status["modules"]["SetupDetectionEngine"] = "running"
        except Exception as e:
            self._status["modules"]["SetupDetectionEngine"] = f"error: {e}"

    def _start_outcome_analysis(self):
        try:
            from zohra.hie.outcome_analysis_engine import outcome_analysis_engine
            outcome_analysis_engine.start()
            self._status["modules"]["OutcomeAnalysisEngine"] = "running"
        except Exception as e:
            self._status["modules"]["OutcomeAnalysisEngine"] = f"error: {e}"

    def _start_pattern_db(self):
        try:
            from zohra.hie.historical_pattern_database import historical_pattern_database
            historical_pattern_database.start()
            self._status["modules"]["HistoricalPatternDatabase"] = "running"
        except Exception as e:
            self._status["modules"]["HistoricalPatternDatabase"] = f"error: {e}"

    def _start_memory(self):
        try:
            from zohra.hie.market_memory_engine import market_memory_engine
            market_memory_engine.start()
            self._status["modules"]["MarketMemoryEngine"] = "running"
        except Exception as e:
            self._status["modules"]["MarketMemoryEngine"] = f"error: {e}"

    def _start_symbol_profiles(self):
        try:
            from zohra.hie.symbol_intelligence_profiles import symbol_intelligence_profiles
            symbol_intelligence_profiles.start()
            self._status["modules"]["SymbolIntelligenceProfiles"] = "running"
        except Exception as e:
            self._status["modules"]["SymbolIntelligenceProfiles"] = f"error: {e}"

    def _start_failure_detector(self):
        try:
            from zohra.hie.failure_pattern_detector import failure_pattern_detector
            failure_pattern_detector.start()
            self._status["modules"]["FailurePatternDetector"] = "running"
        except Exception as e:
            self._status["modules"]["FailurePatternDetector"] = f"error: {e}"

    def _start_calibration(self):
        try:
            from zohra.hie.confidence_calibration_engine import confidence_calibration_engine
            confidence_calibration_engine.start()
            self._status["modules"]["ConfidenceCalibration"] = "running"
        except Exception as e:
            self._status["modules"]["ConfidenceCalibration"] = f"error: {e}"

    def _start_learning(self):
        try:
            from zohra.hie.learning_engine_hie import learning_engine_hie
            learning_engine_hie.start()
            self._status["modules"]["LearningEngineHIE"] = "running"
        except Exception as e:
            self._status["modules"]["LearningEngineHIE"] = f"error: {e}"

    def _start_validation_lab(self):
        try:
            from zohra.learning.strategy_validation_lab import strategy_validation_lab
            strategy_validation_lab.start()
            self._status["modules"]["StrategyValidationLab"] = "running"
        except Exception as e:
            self._status["modules"]["StrategyValidationLab"] = f"error: {e}"

    def _start_evolution_engine(self):
        try:
            from zohra.learning.evolution_engine import evolution_engine
            evolution_engine.start()
            self._status["modules"]["EvolutionEngine"] = "running"
        except Exception as e:
            self._status["modules"]["EvolutionEngine"] = f"error: {e}"

    def _start_smc_research(self):
        try:
            from zohra.agents.smc_research_agent import smc_research_agent
            smc_research_agent.start()
            self._status["modules"]["SMCResearchAgent"] = "running"
        except Exception as e:
            self._status["modules"]["SMCResearchAgent"] = f"error: {e}"

    def _start_trend_research(self):
        try:
            from zohra.agents.trend_research_agent import trend_research_agent
            trend_research_agent.start()
            self._status["modules"]["TrendResearchAgent"] = "running"
        except Exception as e:
            self._status["modules"]["TrendResearchAgent"] = f"error: {e}"

    def _start_session_research(self):
        try:
            from zohra.agents.session_research_agent import session_research_agent
            session_research_agent.start()
            self._status["modules"]["SessionResearchAgent"] = "running"
        except Exception as e:
            self._status["modules"]["SessionResearchAgent"] = f"error: {e}"

    def _start_correlation_research(self):
        try:
            from zohra.agents.correlation_research_agent import correlation_research_agent
            correlation_research_agent.start()
            self._status["modules"]["CorrelationResearchAgent"] = "running"
        except Exception as e:
            self._status["modules"]["CorrelationResearchAgent"] = f"error: {e}"

    def _status_monitor_loop(self):
        """Periodically update aggregate statistics in status dict."""
        while True:
            try:
                self._update_stats()
            except Exception:
                pass
            time.sleep(300)  # Every 5 minutes

    def _update_stats(self):
        try:
            from zohra.hie.historical_data_engine import historical_data_engine
            self._status["total_candles"] = historical_data_engine.get_candle_count()
        except Exception:
            pass
        try:
            from zohra.hie.setup_detection_engine import setup_detection_engine
            self._status["total_setups"] = setup_detection_engine.get_setup_count()
        except Exception:
            pass
        try:
            from zohra.hie.outcome_analysis_engine import outcome_analysis_engine
            self._status["total_outcomes"] = outcome_analysis_engine.get_outcome_count()
        except Exception:
            pass
        try:
            from zohra.hie.historical_pattern_database import historical_pattern_database
            self._status["total_patterns"] = historical_pattern_database.get_stats_count()
        except Exception:
            pass
        try:
            from zohra.hie.symbol_intelligence_profiles import symbol_intelligence_profiles
            self._status["total_profiles"] = symbol_intelligence_profiles.get_profiles_count()
        except Exception:
            pass
        try:
            from zohra.hie.failure_pattern_detector import failure_pattern_detector
            self._status["failure_flags"] = failure_pattern_detector.get_flagged_count()
        except Exception:
            pass

    def status(self) -> Dict:
        """Return current HIE system status."""
        self._update_stats()
        uptime = None
        if self._start_time:
            elapsed = dt.datetime.utcnow() - self._start_time
            hours = int(elapsed.total_seconds() // 3600)
            minutes = int((elapsed.total_seconds() % 3600) // 60)
            uptime = f"{hours}h {minutes}m"
        return {
            **self._status,
            "uptime": uptime,
            "ready": self._started and self._status["total_candles"] > 0
        }

    def is_ready(self) -> bool:
        """True when HIE has loaded enough data to be useful."""
        return self._started and self._status.get("total_candles", 0) > 100


# Singleton
hie_orchestrator = HIEOrchestrator()
