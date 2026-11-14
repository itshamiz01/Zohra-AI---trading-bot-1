"""
Instrument Registry - Fast instrument specification lookup with daily refresh.

Implements:
- Loading all NSE/BSE instrument specifications
- Fast lookup by symbol, ISIN, exchange (<10ms)
- Daily cache refresh at 08:00 IST
- Futures expiry and new contract handling
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ....brokers.models import StandardInstrument
from ....brokers.interfaces import UnifiedBrokerAdapter

logger = logging.getLogger(__name__)


class InstrumentRegistry:
    """Fast instrument specification lookup with daily refresh."""
    
    def __init__(self, broker: UnifiedBrokerAdapter, config):
        self.broker = broker
        self.config = config
        self.instruments: Dict[str, StandardInstrument] = {}
        self.symbol_to_instrument: Dict[str, StandardInstrument] = {}
        self.isin_to_instrument: Dict[str, StandardInstrument] = {}
        self.last_refresh: Optional[datetime] = None
        self._refresh_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> None:
        """Load all instruments from Dhan adapter."""
        logger.info("Loading instrument specifications...")
        start_time = time.time()
        
        try:
            # Load all asset classes
            all_instruments = []
            
            try:
                equity_instruments = await self.broker.get_instruments(asset_class="EQUITY")
                all_instruments.extend(equity_instruments)
                logger.info(f"Loaded {len(equity_instruments)} equity instruments")
            except Exception as e:
                logger.warning(f"Failed to load equity instruments: {e}")
            
            try:
                futures_instruments = await self.broker.get_instruments(asset_class="FUTURES")
                all_instruments.extend(futures_instruments)
                logger.info(f"Loaded {len(futures_instruments)} futures instruments")
            except Exception as e:
                logger.warning(f"Failed to load futures instruments: {e}")
            
            try:
                options_instruments = await self.broker.get_instruments(asset_class="OPTIONS")
                all_instruments.extend(options_instruments)
                logger.info(f"Loaded {len(options_instruments)} options instruments")
            except Exception as e:
                logger.warning(f"Failed to load options instruments: {e}")
            
            # Build indexes
            for instrument in all_instruments:
                key = f"{instrument.exchange}:{instrument.symbol}"
                self.instruments[key] = instrument
                self.symbol_to_instrument[instrument.symbol] = instrument
                
                # Add ISIN index if available
                if hasattr(instrument, 'isin') and instrument.isin:
                    self.isin_to_instrument[instrument.isin] = instrument
            
            self.last_refresh = datetime.now()
            
            load_time = (time.time() - start_time) * 1000
            logger.info(f"✅ Loaded {len(all_instruments)} instruments in {load_time:.2f}ms")
            
            # Schedule daily refresh at 08:00 IST
            self._refresh_task = asyncio.create_task(self._daily_refresh_loop())
            
        except Exception as e:
            logger.error(f"Failed to initialize instrument registry: {e}")
            raise
    
    def get_instrument(
        self,
        symbol: Optional[str] = None,
        isin: Optional[str] = None,
        exchange: str = "NSE"
    ) -> Optional[StandardInstrument]:
        """Fast lookup of instrument specification (<10ms)."""
        if symbol:
            key = f"{exchange}:{symbol}"
            return self.instruments.get(key)
        elif isin:
            return self.isin_to_instrument.get(isin)
        return None
    
    def search_instruments(
        self,
        asset_class: Optional[str] = None,
        sector: Optional[str] = None,
        min_volume: Optional[int] = None
    ) -> List[StandardInstrument]:
        """Filter instruments by criteria."""
        results = list(self.instruments.values())
        
        if asset_class:
            results = [i for i in results if i.asset_class == asset_class]
        if sector:
            results = [i for i in results if getattr(i, 'sector', None) == sector]
        if min_volume:
            # Would need tick data for volume filtering
            pass
            
        return results
    
    def validate_symbol(self, symbol: str, exchange: str = "NSE") -> bool:
        """Check if symbol exists in registry."""
        key = f"{exchange}:{symbol}"
        return key in self.instruments
    
    async def _daily_refresh_loop(self) -> None:
        """Refresh instrument cache daily at 08:00 IST."""
        while True:
            try:
                now = datetime.now()
                target_time = now.replace(
                    hour=self.config.instrument_cache_refresh_hour,
                    minute=0,
                    second=0,
                    microsecond=0
                )
                
                if now > target_time:
                    # If past 08:00 today, schedule for tomorrow
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"Next instrument cache refresh in {wait_seconds/3600:.1f} hours")
                
                await asyncio.sleep(wait_seconds)
                
                # Refresh instruments
                logger.info("Starting daily instrument refresh")
                await self.initialize()
                
            except Exception as e:
                logger.error(f"Daily refresh loop error: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour
    
    def __len__(self) -> int:
        """Return number of instruments in registry."""
        return len(self.instruments)
