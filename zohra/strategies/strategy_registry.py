"""
╔══════════════════════════════════════════════════════════════════════╗
║   ZOHRA — 15-STRATEGY MASTER REGISTRY & METADATA LIBRARY             ║
║   Central metadata registry for all 15 active trading strategies.    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, List, Optional, Any
from zohra.core.enums import StrategyGroup, StrategyName

logger = logging.getLogger("zohra.strategies.registry")


class StrategyMetadata:
    """Structured metadata descriptor for a registered strategy."""

    def __init__(
        self,
        name: str,
        category: str,
        group: str,
        applicable_regimes: List[str],
        applicable_sessions: List[str],
        applicable_timeframes: List[str],
        min_rrr: float = 1.5,
        description: str = "",
        instance: Any = None,
        is_active: bool = True,
        version: str = "2.0.0"
    ):
        self.name = name
        self.category = category
        self.group = group
        self.applicable_regimes = applicable_regimes
        self.applicable_sessions = applicable_sessions
        self.applicable_timeframes = applicable_timeframes
        self.min_rrr = min_rrr
        self.description = description
        self.instance = instance
        self.is_active = is_active
        self.version = version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "group": self.group,
            "applicable_regimes": self.applicable_regimes,
            "applicable_sessions": self.applicable_sessions,
            "applicable_timeframes": self.applicable_timeframes,
            "min_rrr": self.min_rrr,
            "description": self.description,
            "is_active": self.is_active,
            "version": self.version
        }


class StrategyRegistry:
    """
    Master Strategy Registry for Zohra 15-Strategy Confluence Trading OS.
    """

    def __init__(self):
        self._strategies: Dict[str, StrategyMetadata] = {}

    def register(self, meta: StrategyMetadata) -> None:
        """Register a strategy with its metadata."""
        self._strategies[meta.name] = meta
        logger.debug(f"Registered strategy: {meta.name} [Group: {meta.group}] (active={meta.is_active})")

    def get(self, name: str) -> Optional[StrategyMetadata]:
        return self._strategies.get(name)

    def get_instance(self, name: str) -> Optional[Any]:
        meta = self._strategies.get(name)
        return meta.instance if meta else None

    def list_all(self, active_only: bool = True) -> List[StrategyMetadata]:
        if active_only:
            return [m for m in self._strategies.values() if m.is_active]
        return list(self._strategies.values())

    def get_by_group(self, group: str, active_only: bool = True) -> List[StrategyMetadata]:
        return [
            m for m in self._strategies.values()
            if m.group == group and (not active_only or m.is_active)
        ]

    def get_by_regime(self, regime: str, active_only: bool = True) -> List[StrategyMetadata]:
        return [
            m for m in self._strategies.values()
            if (regime.lower() in [r.lower() for r in m.applicable_regimes] or "all" in [r.lower() for r in m.applicable_regimes])
            and (not active_only or m.is_active)
        ]

    def set_active(self, name: str, is_active: bool) -> bool:
        if name in self._strategies:
            self._strategies[name].is_active = is_active
            logger.info(f"Strategy {name} active status set to: {is_active}")
            return True
        return False

    def summary(self) -> Dict[str, Any]:
        return {
            "total_registered": len(self._strategies),
            "active_count": sum(1 for m in self._strategies.values() if m.is_active),
            "groups": {
                group.value: len(self.get_by_group(group.value))
                for group in StrategyGroup
            },
            "strategies": {name: meta.to_dict() for name, meta in self._strategies.items()}
        }


# Singleton registry instance
strategy_registry = StrategyRegistry()
