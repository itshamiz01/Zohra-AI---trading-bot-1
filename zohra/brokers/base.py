"""
Abstract broker adapter — enables multi-broker future support.
All execution goes through this interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BrokerAdapter(ABC):
    """Unified broker interface for Zohra engine."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self):
        ...

    @abstractmethod
    def get_account_summary(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, count: int) -> Any:
        ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> Dict[str, float]:
        ...

    @abstractmethod
    def get_open_positions(self) -> List[Dict]:
        ...

    @abstractmethod
    def open_position(self, order: Dict) -> Dict:
        ...

    @abstractmethod
    def close_position(self, ticket: int, symbol: str, volume: float, direction: str) -> Dict:
        ...

    @abstractmethod
    def modify_stop(self, ticket: int, symbol: str, stop_loss: float, take_profit: Optional[float] = None) -> Dict:
        ...
