from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, Dict

class BaseStrategy(ABC):
    """
    Abstract Base Class for Zohra stateless trading strategies.
    All strategy implementations must inherit from this and implement generate_signal.
    """

    def __init__(self, name: str = "base_strategy"):
        self.name = name

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """
        Analyzes the data and returns a signal proposal or None.
        Returns:
            Dict: {
                "strategy": str,
                "symbol": str,
                "direction": "LONG" | "SHORT",
                "entry_price": float,
                "stop_loss": float,
                "take_profit": float,
                "reason": str,
                "indicators": Dict[str, float]
            } or None
        """
        pass
