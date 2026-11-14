"""
Order Manager - Handles order validation, submission, and state management.

Implements:
- Order validation against instrument specifications
- Support for MARKET, LIMIT, STOP_LOSS, STOP_LIMIT order types
- Order state machine tracking
- Order modification and cancellation
- Execution latency tracking
"""

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from ....brokers.models import StandardOrder, StandardExecution, OrderStatus, ExecutionStatus
from ....brokers.interfaces import UnifiedBrokerAdapter
from .instrument_registry import InstrumentRegistry

logger = logging.getLogger(__name__)


class OrderStateMachine:
    """Manages valid order state transitions."""
    
    VALID_TRANSITIONS = {
        OrderStatus.PENDING: [OrderStatus.OPEN, OrderStatus.FILLED, OrderStatus.REJECTED],
        OrderStatus.OPEN: [
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED
        ],
        OrderStatus.PARTIALLY_FILLED: [
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED
        ],
        OrderStatus.FILLED: [],  # Terminal state
        OrderStatus.CANCELLED: [],  # Terminal state
        OrderStatus.REJECTED: [],  # Terminal state
        OrderStatus.EXPIRED: [],  # Terminal state
        OrderStatus.ERROR: []  # Terminal state
    }
    
    def __init__(self):
        self.order_states: Dict[str, OrderStatus] = {}
    
    def transition(self, order_id: str, new_status: OrderStatus) -> bool:
        """Attempt state transition, return True if valid."""
        current_status = self.order_states.get(order_id, OrderStatus.PENDING)
        
        if new_status in self.VALID_TRANSITIONS.get(current_status, []):
            self.order_states[order_id] = new_status
            return True
        else:
            logger.warning(
                f"Invalid order state transition: {order_id} "
                f"{current_status.value} → {new_status.value}"
            )
            return False


class OrderManager:
    """Manages order lifecycle with validation and state tracking."""
    
    def __init__(
        self,
        broker: UnifiedBrokerAdapter,
        instrument_registry: InstrumentRegistry,
        config
    ):
        self.broker = broker
        self.instruments = instrument_registry
        self.config = config
        self.orders: Dict[str, StandardExecution] = {}
        self.order_state_machine = OrderStateMachine()
        
    async def submit_order(self, order: StandardOrder) -> StandardExecution:
        """Validate and submit order to Dhan adapter."""
        start_time = time.time()
        
        # Phase 1: Validate instrument exists
        instrument = self.instruments.get_instrument(order.symbol)
        if not instrument:
            return StandardExecution(
                order_id=order.order_id,
                symbol=order.symbol,
                direction=order.direction,
                status=ExecutionStatus.REJECTED,
                error="INVALID_INSTRUMENT",
                broker=self.broker.name,
                timestamp=datetime.now()
            )
        
        # Phase 2: Validate quantity against lot size
        validation_error = self._validate_quantity(order.volume, instrument)
        if validation_error:
            return StandardExecution(
                order_id=order.order_id,
                symbol=order.symbol,
                direction=order.direction,
                status=ExecutionStatus.REJECTED,
                error=validation_error,
                broker=self.broker.name,
                timestamp=datetime.now()
            )
        
        # Phase 3: Validate price against tick size
        if order.price and order.price > 0:
            validation_error = self._validate_price(order.price, instrument)
            if validation_error:
                return StandardExecution(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    direction=order.direction,
                    status=ExecutionStatus.REJECTED,
                    error=validation_error,
                    broker=self.broker.name,
                    timestamp=datetime.now()
                )
        
        # Phase 4: Submit to broker
        try:
            execution = await self.broker.place_order(order)
            execution.latency_ms = (time.time() - start_time) * 1000
            
            # Track order state
            if execution.status != ExecutionStatus.REJECTED:
                self.orders[execution.order_id] = execution
                self.order_state_machine.transition(
                    execution.order_id,
                    OrderStatus.FILLED if execution.status == ExecutionStatus.SUCCESS else OrderStatus.PENDING
                )
            
            logger.info(
                f"✅ Order submitted: {execution.order_id} | {order.symbol} | "
                f"Status: {execution.status.value} | Latency: {execution.latency_ms:.2f}ms"
            )
            return execution
            
        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            return StandardExecution(
                order_id=order.order_id,
                symbol=order.symbol,
                direction=order.direction,
                status=ExecutionStatus.FAILED,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
                broker=self.broker.name,
                timestamp=datetime.now()
            )
    
    def _validate_quantity(self, volume: float, instrument) -> Optional[str]:
        """Validate quantity against lot size constraints."""
        min_lot = instrument.min_lot
        lot_step = instrument.lot_step
        
        if volume < min_lot:
            return f"QUANTITY_BELOW_MIN_LOT: {volume} < {min_lot}"
        
        # Check if volume is multiple of lot step
        if lot_step > 0:
            remainder = (volume - min_lot) % lot_step
            if remainder > 0.0001:  # Small tolerance for floating point
                return f"QUANTITY_NOT_LOT_MULTIPLE: {volume} not multiple of {lot_step}"
        
        return None
    
    def _validate_price(self, price: float, instrument) -> Optional[str]:
        """Validate price against tick size constraints."""
        tick_size = instrument.point
        
        if tick_size > 0:
            remainder = price % tick_size
            if remainder > 0.0001:  # Small tolerance for floating point
                return f"PRICE_NOT_TICK_MULTIPLE: {price} not multiple of {tick_size}"
        
        return None
    
    async def modify_order(
        self,
        order_id: str,
        new_price: Optional[float] = None,
        new_volume: Optional[float] = None
    ) -> StandardExecution:
        """Modify pending order."""
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        current_order = self.orders[order_id]
        
        # Can only modify pending/open orders
        if current_order.status not in [ExecutionStatus.PARTIAL]:
            return StandardExecution(
                order_id=order_id,
                symbol=current_order.symbol,
                direction=current_order.direction,
                status=ExecutionStatus.REJECTED,
                error="ORDER_NOT_MODIFIABLE",
                broker=self.broker.name,
                timestamp=datetime.now()
            )
        
        # Submit modification to broker
        try:
            execution = await self.broker.modify_order(order_id, new_price, new_volume)
            
            # Update state
            if execution.status != ExecutionStatus.REJECTED:
                self.orders[order_id] = execution
            
            logger.info(f"Order {order_id} modified")
            return execution
            
        except Exception as e:
            logger.error(f"Order modification failed: {e}")
            raise
    
    async def cancel_order(self, order_id: str) -> StandardExecution:
        """Cancel pending order."""
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        try:
            execution = await self.broker.cancel_order(order_id)
            
            # Update state
            if execution.status == ExecutionStatus.SUCCESS:
                self.order_state_machine.transition(order_id, OrderStatus.CANCELLED)
            
            logger.info(f"Order {order_id} cancelled")
            return execution
            
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            raise
    
    def get_pending_orders(self) -> List[StandardExecution]:
        """Return all pending orders."""
        return [
            order for order in self.orders.values()
            if order.status in [ExecutionStatus.PARTIAL]
        ]
