"""
╔══════════════════════════════════════════════════════════════╗
║        INDIAN MARKET ENGINE - INSTRUMENT REGISTRY            ║
║      Fast instrument specification lookup with caching        ║
╚══════════════════════════════════════════════════════════════╝

The Instrument Registry provides:
- Fast instrument specification lookup (<10ms)
- Daily automatic cache refresh at market open  
- Support for equity, futures, and options instruments
- Multiple search methods (symbol, ISIN, exchange)
- Instrument validation for order processing
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ...brokers.interfaces import UnifiedBrokerAdapter
from ..config import EngineConfig
from ..models import InstrumentSpec, AssetClass

logger = logging.getLogger(__name__)


class InstrumentRegistry:
    """
    Fast instrument specification lookup with daily refresh.
    
    Maintains a local cache of all tradeable instruments for high-speed
    lookups during order processing and validation.
    """
    
    def __init__(self, broker: UnifiedBrokerAdapter, config: EngineConfig):
        self.broker = broker
        self.config = config
        
        # Main instrument storage
        self.instruments: Dict[str, InstrumentSpec] = {}
        self.symbol_to_instrument: Dict[str, InstrumentSpec] = {}
        self.isin_to_instrument: Dict[str, InstrumentSpec] = {}
        
        # Cache metadata
        self.last_refresh: Optional[datetime] = None
        self.is_initialized = False
        self._refresh_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> None:
        """Load all instruments from Dhan adapter."""
        logger.info("🔄 Loading instrument specifications...")
        start_time = time.time()
        
        try:
            # Load all asset classes
            await self._load_instruments_by_asset_class(AssetClass.EQUITY)
            await self._load_instruments_by_asset_class(AssetClass.FUTURES)
            await self._load_instruments_by_asset_class(AssetClass.OPTIONS)
            
            self.last_refresh = datetime.now()
            self.is_initialized = True
            
            load_time = (time.time() - start_time) * 1000
            logger.info(f"✅ Loaded {len(self.instruments)} instruments in {load_time:.2f}ms")
            
            # Schedule daily refresh
            self._refresh_task = asyncio.create_task(self._daily_refresh_loop())
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize instrument registry: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the instrument registry and cancel refresh tasks."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("Instrument Registry stopped")
    
    async def _load_instruments_by_asset_class(self, asset_class: AssetClass) -> None:
        """Load instruments for a specific asset class."""
        try:
            logger.debug(f"Loading {asset_class.value} instruments...")
            
            # Get instruments from broker (this is a placeholder - actual implementation
            # would depend on Dhan API structure)
            instruments_data = await self._fetch_instruments_from_broker(asset_class)
            
            for instrument_data in instruments_data:
                instrument_spec = self._parse_instrument_data(instrument_data, asset_class)
                if instrument_spec:
                    self._store_instrument(instrument_spec)
            
            logger.debug(f"Loaded {len([i for i in self.instruments.values() if i.asset_class == asset_class])} {asset_class.value} instruments")
            
        except Exception as e:
            logger.error(f"Error loading {asset_class.value} instruments: {e}")
            # Don't raise - allow other asset classes to load
    
    async def _fetch_instruments_from_broker(self, asset_class: AssetClass) -> List[Dict]:
        """
        Fetch instrument data from broker adapter.
        
        This is a placeholder implementation. In practice, this would call
        the Dhan API to get instrument specifications.
        """
        # For now, return sample data for demonstration
        # In real implementation, this would call Dhan API endpoints
        sample_instruments = []
        
        if asset_class == AssetClass.EQUITY:
            sample_instruments = [
                {
                    "symbol": "RELIANCE",
                    "trading_symbol": "RELIANCE-EQ",
                    "isin": "INE002A01018",
                    "segment": "NSE_EQ",
                    "lot_size": 1,
                    "tick_size": 0.05,
                    "sector": "Energy"
                },
                {
                    "symbol": "TCS",
                    "trading_symbol": "TCS-EQ",
                    "isin": "INE467B01029",
                    "segment": "NSE_EQ",
                    "lot_size": 1,
                    "tick_size": 0.05,
                    "sector": "IT"
                }
            ]
        elif asset_class == AssetClass.FUTURES:
            sample_instruments = [
                {
                    "symbol": "NIFTY25JUN24000FUT",
                    "trading_symbol": "NIFTY 25 JUN 2024 FUT",
                    "segment": "NSE_FNO",
                    "lot_size": 25,
                    "tick_size": 0.05,
                    "expiry_date": "2024-06-27"
                }
            ]
        
        return sample_instruments
    
    def _parse_instrument_data(self, data: Dict, asset_class: AssetClass) -> Optional[InstrumentSpec]:
        """Parse raw instrument data into InstrumentSpec object."""
        try:
            # Parse expiry date if present
            expiry_date = None
            if "expiry_date" in data and data["expiry_date"]:
                try:
                    expiry_date = datetime.strptime(data["expiry_date"], "%Y-%m-%d")
                except ValueError:
                    logger.warning(f"Invalid expiry date format: {data['expiry_date']}")
            
            # Determine exchange from segment
            exchange = "NSE"
            if data.get("segment", "").startswith("BSE"):
                exchange = "BSE"
            elif data.get("segment", "").startswith("MCX"):
                exchange = "MCX"
            
            return InstrumentSpec(
                symbol=data["symbol"],
                exchange=exchange,
                asset_class=asset_class,
                lot_size=int(data.get("lot_size", 1)),
                tick_size=float(data.get("tick_size", 0.05)),
                contract_size=float(data.get("contract_size", 1.0)),
                margin_required=float(data.get("margin_required", 10000.0)),
                expiry_date=expiry_date,
                sector=data.get("sector"),
                isin=data.get("isin"),
                trading_symbol=data.get("trading_symbol"),
                segment=data.get("segment")
            )
            
        except Exception as e:
            logger.error(f"Error parsing instrument data {data}: {e}")
            return None
    
    def _store_instrument(self, instrument: InstrumentSpec) -> None:
        """Store instrument in all lookup indexes."""
        # Primary key: exchange:symbol
        key = f"{instrument.exchange}:{instrument.symbol}"
        self.instruments[key] = instrument
        
        # Symbol lookup
        self.symbol_to_instrument[instrument.symbol] = instrument
        
        # ISIN lookup (if available)
        if instrument.isin:
            self.isin_to_instrument[instrument.isin] = instrument
    
    def get_instrument(
        self,
        symbol: Optional[str] = None,
        isin: Optional[str] = None,
        exchange: str = "NSE"
    ) -> Optional[InstrumentSpec]:
        """
        Fast lookup of instrument specification (<10ms).
        
        Args:
            symbol: Instrument symbol
            isin: ISIN code
            exchange: Exchange name (default: NSE)
            
        Returns:
            InstrumentSpec if found, None otherwise
        """
        start_time = time.time()
        
        try:
            if symbol:
                key = f"{exchange}:{symbol}"
                result = self.instruments.get(key)
                if not result:
                    # Fallback to symbol-only lookup
                    result = self.symbol_to_instrument.get(symbol)
            elif isin:
                result = self.isin_to_instrument.get(isin)
            else:
                return None
            
            lookup_time = (time.time() - start_time) * 1000
            if lookup_time > 10:
                logger.warning(f"Instrument lookup took {lookup_time:.2f}ms (>10ms threshold)")
            
            return result
            
        except Exception as e:
            logger.error(f"Error looking up instrument: {e}")
            return None
    
    def search_instruments(
        self,
        asset_class: Optional[AssetClass] = None,
        sector: Optional[str] = None,
        exchange: Optional[str] = None,
        min_volume: Optional[int] = None
    ) -> List[InstrumentSpec]:
        """Filter instruments by criteria."""
        results = list(self.instruments.values())
        
        if asset_class:
            results = [i for i in results if i.asset_class == asset_class]
        
        if sector:
            results = [i for i in results if i.sector and i.sector.lower() == sector.lower()]
        
        if exchange:
            results = [i for i in results if i.exchange.lower() == exchange.lower()]
        
        # Volume filtering would require real-time data
        if min_volume:
            logger.warning("Volume filtering not implemented - requires real-time data")
        
        return results
    
    def validate_symbol(self, symbol: str, exchange: str = "NSE") -> bool:
        """Check if symbol exists in registry."""
        instrument = self.get_instrument(symbol=symbol, exchange=exchange)
        return instrument is not None
    
    def get_lot_size(self, symbol: str, exchange: str = "NSE") -> int:
        """Get lot size for a symbol."""
        instrument = self.get_instrument(symbol=symbol, exchange=exchange)
        return instrument.lot_size if instrument else 1
    
    def get_tick_size(self, symbol: str, exchange: str = "NSE") -> float:
        """Get tick size for a symbol."""
        instrument = self.get_instrument(symbol=symbol, exchange=exchange)
        return float(instrument.tick_size) if instrument else 0.05
    
    def get_margin_required(self, symbol: str, exchange: str = "NSE") -> float:
        """Get margin requirement for a symbol."""
        instrument = self.get_instrument(symbol=symbol, exchange=exchange)
        return float(instrument.margin_required) if instrument else 10000.0
    
    def get_registry_stats(self) -> Dict:
        """Get registry statistics."""
        total_instruments = len(self.instruments)
        
        # Count by asset class
        asset_class_counts = {}
        for asset_class in AssetClass:
            count = len([i for i in self.instruments.values() if i.asset_class == asset_class])
            asset_class_counts[asset_class.value] = count
        
        # Count by exchange
        exchange_counts = {}
        for instrument in self.instruments.values():
            exchange_counts[instrument.exchange] = exchange_counts.get(instrument.exchange, 0) + 1
        
        return {
            "total_instruments": total_instruments,
            "by_asset_class": asset_class_counts,
            "by_exchange": exchange_counts,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "is_initialized": self.is_initialized,
            "cache_age_hours": (datetime.now() - self.last_refresh).total_seconds() / 3600 if self.last_refresh else None
        }
    
    async def _daily_refresh_loop(self) -> None:
        """Refresh instrument cache daily at configured hour."""
        while True:
            try:
                now = datetime.now()
                target_time = now.replace(
                    hour=self.config.instrument_cache_refresh_hour,
                    minute=0,
                    second=0,
                    microsecond=0
                )
                
                # If past the refresh time today, schedule for tomorrow
                if now > target_time:
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"Next instrument cache refresh scheduled for {target_time}")
                
                await asyncio.sleep(wait_seconds)
                
                # Perform refresh
                logger.info("🔄 Starting scheduled instrument cache refresh")
                await self.refresh_cache()
                
            except asyncio.CancelledError:
                logger.info("Daily refresh loop cancelled")
                break
            except Exception as e:
                logger.error(f"Daily refresh loop error: {e}")
                # Wait 1 hour before retrying
                await asyncio.sleep(3600)
    
    async def refresh_cache(self) -> bool:
        """Manually refresh the instrument cache."""
        try:
            logger.info("🔄 Refreshing instrument cache...")
            
            # Clear existing cache
            old_count = len(self.instruments)
            self.instruments.clear()
            self.symbol_to_instrument.clear()
            self.isin_to_instrument.clear()
            
            # Reload all instruments
            await self._load_instruments_by_asset_class(AssetClass.EQUITY)
            await self._load_instruments_by_asset_class(AssetClass.FUTURES)
            await self._load_instruments_by_asset_class(AssetClass.OPTIONS)
            
            self.last_refresh = datetime.now()
            new_count = len(self.instruments)
            
            logger.info(f"✅ Cache refreshed: {old_count} → {new_count} instruments")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to refresh instrument cache: {e}")
            return False