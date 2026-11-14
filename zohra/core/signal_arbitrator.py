"""
╔══════════════════════════════════════════════════════════════════════╗
║        ZOHRA — SIGNAL ARBITRATOR & CONFLUENCE ADAPTER                ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from zohra.core.confluence_engine import (
    ConfluenceEngine,
    ConfluenceDecision,
    ArbitrationResult,
    confluence_engine,
    signal_arbitrator
)

# Alias for backward compatibility
SignalArbitrator = ConfluenceEngine

__all__ = [
    "SignalArbitrator",
    "ConfluenceEngine",
    "ConfluenceDecision",
    "ArbitrationResult",
    "confluence_engine",
    "signal_arbitrator"
]
