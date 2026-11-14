"""
Position Manager - Tracks positions with real-time P&L calculation.

Implements:
- Real-time position registry
- Floating P&L calculation on tick updates
- Position lifecycle management (opened, modified, closed)
- Stop loss and take profit trigger detection
- Position queries with filtering
"""

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Callable

from ....brokers.models import StandardPosition, StandardTick
from ....brokers.interfaces import UnifiedBrokerAdapter

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages position lifecycle and P&L tracking."""
    
    def __init__(self, broker: UnifiedBrokerAdapter, config):
        self.broker = broker
        self.config = config
        self.positions: Dict[str, Dict] = {}
        self.closed_positions: List[Dict] = []
        self._position_opened_handlers: List[Callable] = []
        self._position_closed_handlers: List[Callable] = []
        
    async def sync_positions(self) -> None:
        """Synchronize positions with broker."""
        try:
            broker_positions = await self.broker.get_positions()
            
            # Update local registry
            for position in broker_positions:
                pos_key = str(position.get('ticket', position.get('position_id', '')))
                if pos_key:
                    self.positions[pos_key] = position.to_dict() if hasattr(position, 'to_dict') else position
            
            logger.debug(f"Synced {len(broker_positions)} positions")
        except Exception as e:
            logger.error(f"Position sync failed: {e}")
    
    def get_position(self, ticket: str) -> Optional[Dict]:
        """Get position by ticket."""
        return self.positions.get(ticket)
    
    def get_all_positions(self) -> List[Dict]:
        """Return all open positions."""
        return list(self.positions.values())
    
    def query_positions(
        self,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        ticket: Optional[str] = None
    ) -> List[Dict]:
        """Query positions with filtering."""
        results = list(self.positions.values())
        
        if ticket:
            position = self.positions.get(ticket)
            return [position] if position else []
        
        if symbol:
            results = [p for p in results if p.get('symbol') == symbol]
        
        if asset_class:
            results = [p for p in results if p.get('asset_class') == asset_class]
        
        return results
    
    async def update_position_price(self, tick: StandardTick) -> None:
        """Update position with current price and recalculate P&L."""
        start_time = time.time()
        
        for pos_key, position in self.positions.items():
            if position.get('symbol') == tick.symbol:
                # Update current price
                position['current_price'] = tick.last
                
                # Calculate floating P&L
                entry_price = position.get('entry_price', 0.0)
                quantity = position.get('volume', 0.0)
                direction = position.get('direction', 'LONG')
                
                if direction == "LONG":
                    pnl_per_unit = tick.last - entry_price
                else:  # SHORT
                    pnl_per_unit = entry_price - tick.last
                
                position['pnl'] = pnl_per_unit * quantity
                position['profit'] = position['pnl']
                
                # Update holding time
                if 'open_time' in position and position['open_time']:
                    try:
                        if isinstance(position['open_time'], str):
                            open_time = datetime.fromisoformat(position['open_time'])
                        else:
                            open_time = position['open_time']
                        position['holding_seconds'] = int(
                            (datetime.now() - open_time).total_seconds()
                        )
                    except:
                        pass
        
        update_time = (time.time() - start_time) * 1000
        
        if update_time > self.config.max_position_update_latency_ms:
            logger.warning(
                f"Position update took {update_time:.2f}ms "
                f"(>{self.config.max_position_update_latency_ms}ms threshold)"
            )
    
    async def on_position_opened(self, position: StandardPosition) -> None:
        """Handle new position opened event."""
        pos_dict = position.to_dict() if hasattr(position, 'to_dict') else position
        pos_key = str(pos_dict.get('ticket', pos_dict.get('position_id', '')))
        
        if pos_key:
            self.positions[pos_key] = pos_dict
            logger.info(
                f"📈 Position opened: {pos_key} | {pos_dict.get('symbol')} | "
                f"{pos_dict.get('direction')} | {pos_dict.get('volume')}@{pos_dict.get('entry_price')}"
            )
            
            # Notify handlers
            for handler in self._position_opened_handlers:
                try:
                    await handler(position)
                except Exception as e:
                    logger.error(f"Position opened handler error: {e}")
    
    async def on_position_closed(
        self,
        ticket: str,
        exit_price: float,
        exit_time: datetime
    ) -> None:
        """Handle position closed event."""
        if ticket not in self.positions:
            logger.warning(f"Position {ticket} not found for closure")
            return
        
        position = self.positions[ticket]
        
        # Calculate realized P&L
        entry_price = position.get('entry_price', 0.0)
        volume = position.get('volume', 0.0)
        direction = position.get('direction', 'LONG')
        
        if direction == "LONG":
            pnl_per_unit = exit_price - entry_price
        else:  # SHORT
            pnl_per_unit = entry_price - exit_price
        
        position['realized_pnl'] = pnl_per_unit * volume
        position['exit_price'] = exit_price
        position['exit_time'] = exit_time
        
        # Calculate holding time
        if 'open_time' in position and position['open_time']:
            try:
                if isinstance(position['open_time'], str):
                    open_time = datetime.fromisoformat(position['open_time'])
                else:
                    open_time = position['open_time']
                position['holding_seconds'] = int(
                    (exit_time - open_time).total_seconds()
                )
            except:
                position['holding_seconds'] = 0
        
        # Move to closed positions
        self.closed_positions.append(position)
        del self.positions[ticket]
        
        logger.info(
            f"📉 Position closed: {ticket} | "
            f"P&L: {position['realized_pnl']} | "
            f"Holding time: {position.get('holding_seconds', 0)}s"
        )
        
        # Notify handlers
        for handler in self._position_closed_handlers:
            try:
                await handler(position)
            except Exception as e:
                logger.error(f"Position closed handler error: {e}")
    
    async def check_sl_tp_triggers(self) -> List[str]:
        """Check if any stop loss or take profit levels are hit."""
        triggered_tickets = []
        
        for ticket, position in self.positions.items():
            current_price = position.get('current_price', 0.0)
            stop_loss = position.get('stop_loss', 0.0)
            take_profit = position.get('take_profit', 0.0)
            direction = position.get('direction', 'LONG')
            
            # Check stop loss
            if stop_loss and stop_loss > 0:
                if direction == "LONG" and current_price <= stop_loss:
                    logger.info(f"🛑 Stop loss triggered for {ticket}")
                    triggered_tickets.append(ticket)
                elif direction == "SHORT" and current_price >= stop_loss:
                    logger.info(f"🛑 Stop loss triggered for {ticket}")
                    triggered_tickets.append(ticket)
            
            # Check take profit
            if take_profit and take_profit > 0:
                if direction == "LONG" and current_price >= take_profit:
                    logger.info(f"🎯 Take profit triggered for {ticket}")
                    triggered_tickets.append(ticket)
                elif direction == "SHORT" and current_price <= take_profit:
                    logger.info(f"🎯 Take profit triggered for {ticket}")
                    triggered_tickets.append(ticket)
        
        return triggered_tickets
    
    def calculate_exposure(self) -> Dict[str, Decimal]:
        """Calculate gross and net exposure."""
        gross_exposure = Decimal(0)
        net_exposure = Decimal(0)
        
        for position in self.positions.values():
            current_price = position.get('current_price', 0.0)
            volume = position.get('volume', 0.0)
            direction = position.get('direction', 'LONG')
            
            position_value = Decimal(str(current_price * volume))
            
            gross_exposure += abs(position_value)
            
            if direction == "LONG":
                net_exposure += position_value
            else:  # SHORT
                net_exposure -= position_value
        
        return {
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure
        }
    
    def register_position_opened_handler(self, handler: Callable) -> None:
        """Register handler for position opened events."""
        self._position_opened_handlers.append(handler)
    
    def register_position_closed_handler(self, handler: Callable) -> None:
        """Register handler for position closed events."""
        self._position_closed_handlers.append(handler)
