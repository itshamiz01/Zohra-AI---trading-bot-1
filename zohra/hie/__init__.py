"""
╔══════════════════════════════════════════════════════════════════════╗
║          ZOHRA — HISTORICAL INTELLIGENCE ENGINE (HIE)               ║
║   An additive intelligence layer — never modifies existing logic    ║
╚══════════════════════════════════════════════════════════════════════╝

Package exports for convenient import of all HIE singletons.
"""

# Lazy singletons — imported on first use so startup errors are non-fatal
def _lazy(module_path: str, attr: str):
    """Return a lazy proxy object that imports only when accessed."""
    class LazyProxy:
        _instance = None
        def __getattr__(self, name):
            if self._instance is None:
                import importlib
                mod = importlib.import_module(module_path)
                self._instance = getattr(mod, attr)
            return getattr(self._instance, name)
        def __call__(self, *args, **kwargs):
            if self._instance is None:
                import importlib
                mod = importlib.import_module(module_path)
                self._instance = getattr(mod, attr)
            return self._instance(*args, **kwargs)
    return LazyProxy()


from zohra.hie.historical_data_engine import historical_data_engine
from zohra.hie.market_replay_engine import market_replay_engine
from zohra.hie.setup_detection_engine import setup_detection_engine
from zohra.hie.outcome_analysis_engine import outcome_analysis_engine
from zohra.hie.historical_pattern_database import historical_pattern_database
from zohra.hie.market_memory_engine import market_memory_engine
from zohra.hie.symbol_intelligence_profiles import symbol_intelligence_profiles
from zohra.hie.trade_similarity_engine import trade_similarity_engine
from zohra.hie.historical_intelligence_scoring import historical_intelligence_scoring
from zohra.hie.learning_engine_hie import learning_engine_hie
from zohra.hie.failure_pattern_detector import failure_pattern_detector
from zohra.hie.confidence_calibration_engine import confidence_calibration_engine
from zohra.hie.hie_orchestrator import hie_orchestrator

__all__ = [
    "historical_data_engine",
    "market_replay_engine",
    "setup_detection_engine",
    "outcome_analysis_engine",
    "historical_pattern_database",
    "market_memory_engine",
    "symbol_intelligence_profiles",
    "trade_similarity_engine",
    "historical_intelligence_scoring",
    "learning_engine_hie",
    "failure_pattern_detector",
    "confidence_calibration_engine",
    "hie_orchestrator",
]
