"""
Thread-safe MetaTrader 5 module wrapper.
Provides serialized access to the MT5 API to prevent socket corruption and disconnects.
"""

import sys
import logging
import threading

logger = logging.getLogger("zohra.mt5_conn")

try:
    import MetaTrader5 as raw_mt5
    MT5_AVAILABLE = True
except ImportError:
    raw_mt5 = None
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 package not installed. Wrapper running in mock mode.")

# Global lock to serialize all calls to MetaTrader5 API
mt5_lock = threading.Lock()

class ThreadSafeMT5Wrapper:
    def __init__(self, module, lock):
        self._module = module
        self._lock = lock

    def __getattr__(self, name):
        if self._module is None:
            raise AttributeError(f"MetaTrader5 is not installed, cannot access attribute '{name}'")
        
        val = getattr(self._module, name)
        # If it is a callable function, wrap it with the lock
        if callable(val):
            def locked_call(*args, **kwargs):
                acquired = self._lock.acquire(timeout=2.0)
                if not acquired:
                    logger.warning(f"MT5 call '{name}' timed out waiting for lock")
                    return None
                try:
                    if kwargs:
                        return val(*args, **kwargs)
                    return val(*args)
                finally:
                    self._lock.release()
            return locked_call
        # Otherwise return the constant/attribute directly
        return val

if MT5_AVAILABLE:
    mt5 = ThreadSafeMT5Wrapper(raw_mt5, mt5_lock)
else:
    mt5 = None
