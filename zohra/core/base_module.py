# zohra/core/base_module.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class ZohraModule(ABC):
    """
    Abstract base class for all modular features in ZOHRA OS.
    If a module crashes, it should be sandboxed so the rest of the OS continues working.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True

    @abstractmethod
    def initialize(self) -> bool:
        """Called during core startup. Returns True if successfully initialized."""
        pass

    @abstractmethod
    def shutdown(self) -> bool:
        """Called during core shutdown. Returns True if successfully shutdown."""
        pass

    def on_event(self, event_type: str, data: Any):
        """Optional event listener called by the central Event Bus."""
        pass

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic health information for the module."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "status": "active" if self.enabled else "disabled"
        }
