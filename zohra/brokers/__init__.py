"""
╔══════════════════════════════════════════════════════════════╗
║         ZOHRA BROKERS — MARKET ABSTRACTION LAYER            ║
║  Auto-registration of broker adapters based on config        ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import logging

logger = logging.getLogger("zohra.brokers")

# ── Core MAL imports ──────────────────────────────────────
from zohra.brokers.interfaces import UnifiedBrokerAdapter
from zohra.brokers.models import (
    StandardOrder, StandardTrade, StandardPosition,
    StandardTick, StandardCandle, StandardBalance,
    StandardInstrument, StandardExecution, StandardPortfolio,
    BrokerError,
)
from zohra.brokers.manager import BrokerManager, broker_manager
from zohra.brokers.broker_logger import broker_logger
from zohra.brokers.resilience import reconnection_manager

# ── Legacy imports (backward compatibility) ───────────────
from zohra.brokers.base import BrokerAdapter
from zohra.brokers.mt5_broker import MT5Broker, mt5_broker

# Alias for compatibility
MT5BrokerAdapter = MT5Broker

# ── Conditional adapter imports ───────────────────────────
try:
    from zohra.brokers.ibkr_adapter import IBKRBrokerAdapter, ibkr_broker
except ImportError:
    IBKRBrokerAdapter = None
    ibkr_broker = None

try:
    from zohra.brokers.dhan_adapter import DhanAdapter, dhan_broker
except ImportError:
    DhanAdapter = None
    dhan_broker = None

try:
    from zohra.brokers.coindcx_adapter import CoinDCXAdapter, coindcx_broker
except ImportError:
    CoinDCXAdapter = None
    coindcx_broker = None


# ── Auto-registration ────────────────────────────────────
# Register MT5 adapter by default (preserving existing behavior)
broker_manager.register_adapter("mt5", mt5_broker)

# Read ACTIVE_BROKERS from environment to register additional adapters
_active_brokers = os.getenv("ACTIVE_BROKERS", "mt5").lower().split(",")
_active_brokers = [b.strip() for b in _active_brokers if b.strip()]

if "dhan" in _active_brokers and dhan_broker is not None:
    broker_manager.register_adapter("dhan", dhan_broker)
    logger.info("Dhan adapter registered")

if "coindcx" in _active_brokers and coindcx_broker is not None:
    broker_manager.register_adapter("coindcx", coindcx_broker)
    logger.info("CoinDCX adapter registered")

if "ibkr" in _active_brokers and ibkr_broker is not None:
    broker_manager.register_adapter("ibkr", ibkr_broker)
    logger.info("IBKR adapter registered")

# Set default broker from environment
_default_broker = os.getenv("DEFAULT_BROKER", "mt5").lower().strip()
if _default_broker in broker_manager.get_registered_brokers():
    broker_manager.set_default(_default_broker)


__all__ = [
    # MAL Core
    "UnifiedBrokerAdapter",
    "BrokerManager", "broker_manager",
    "broker_logger", "reconnection_manager",
    # Models
    "StandardOrder", "StandardTrade", "StandardPosition",
    "StandardTick", "StandardCandle", "StandardBalance",
    "StandardInstrument", "StandardExecution", "StandardPortfolio",
    "BrokerError",
    # Legacy
    "BrokerAdapter", "MT5Broker", "mt5_broker", "MT5BrokerAdapter",
    # Conditional
    "IBKRBrokerAdapter", "ibkr_broker",
    "DhanAdapter", "dhan_broker",
    "CoinDCXAdapter", "coindcx_broker",
]
