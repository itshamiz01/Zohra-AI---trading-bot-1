"""
╔══════════════════════════════════════════════════════════════╗
║                      ZOHRA TRADING ENGINES                   ║
║           Market-specific trading engine implementations      ║
║           + ZOHRA Unified System Engines                      ║
╚══════════════════════════════════════════════════════════════╝

This package contains:
- indian_market_engine: For NSE/BSE equity, futures, and options
- market_data_service: Centralized market data ingestion & caching
- strategy_engine: Unified 15-strategy signal generation
- risk_decision_engine: Risk evaluation & per-account lot sizing
- account_worker: Isolated per-account MT5 execution workers
- supervisor: Process lifecycle management
"""

try:
    from .indian_market_engine import IndianMarketEngine
except ImportError:
    IndianMarketEngine = None

__all__ = [
    'IndianMarketEngine',
    # Unified system engines are imported on-demand to avoid circular imports
    # Use: from zohra.engines.supervisor import ZohraSupervisor
    # Use: from zohra.engines.market_data_service import MarketDataService
    # Use: from zohra.engines.strategy_engine import UnifiedStrategyEngine
    # Use: from zohra.engines.risk_decision_engine import RiskDecisionEngine
    # Use: from zohra.engines.account_worker import AccountWorker
]