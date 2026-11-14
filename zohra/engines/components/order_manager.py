"""
╔══════════════════════════════════════════════════════════════╗
║          INDIAN MARKET ENGINE - ORDER MANAGER                ║
║     Order validation, execution, and state management         ║
╚══════════════════════════════════════════════════════════════╝

The Order Manager handles:
- Order validation against instrument specifications
- Order execution through Dhan adapter
- Order state machine tracking (NEW → PENDING → FILLED/CANCELLED/REJECTED)
- Order modification and cancellation
- Execution latency tracking
- Order status event emission
"""

import asyncio
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from ...brokers.interfaces import UnifiedBrokerAdapter
from ...brokers.models import StandardOrder, StandardExecution, ExecutionStatus, OrderStatus
from ..config import EngineConfig
from ..models import LatencyMetrics
from .instrument_registry import InstrumentRegistry

logger = logging.getLogger(__name__)


class OrderStateMachine:
    """Manages valid order state transitions."""
    
    VALID_TRANSITIONS = {
        OrderStatus.PENDING: [
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED
        ],
        OrderStatus.OPEN: [
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
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
        
        # Always allow first transition from PENDING
        if current_status == OrderStatus.PENDING or new_status in self.VALID_TRANSITIONS.get(current_status, []):
            self.order_states[order_id] = new_status
            return True
        else:
            logger.warning(
                f"Invalid order state transition: {order_id} "
                f"{current_status.value} → {new_status.value}"
            )
            return False
    
    def get_state(self, order_id: str) -> OrderStatus:
        """Get current state of an order."""
        return self.order_states.get(order_id, OrderStatus.PENDING)


class OrderManager:
    """
    Manages order lifecycle with validation and state tracking.
    
    Validates orders against instrument specifications, submits to broker,
    and tracks order state through completion or cancellation.
    """
    
    def __init__(
        self,
        broker: UnifiedBrokerAdapter,
        instrument_registry: InstrumentRegistry,
        config: EngineConfig
    ):
        self.broker = broker
        self.instruments = instrument_registry
        self.config = config
        
        # Order tracking
        self.orders: Dict[str, StandardExecution] = {}
        self.order_state_machine = OrderStateMachine()
        
        # Performance tracking
        self.total_orders_submitted = 0
        self.total_orders_filled = 0
        self.total_orders_rejected = 0
        self.execution_latencies: List[float] = []
        
    async def submit_order(self, order: StandardOrder) -> StandardExecution:
        """
        Validate and submit order to Dhan adapter.
        
        Args:
            order: Standardized order to submit
            
        Returns:
            StandardExecution with execution result
        """
        start_time = time.time()
        self.total_orders_submitted += 1
        
        logger.info(f"📋 Submitting order: {order.symbol} {order.side.value} {order.volume}@{order.price}")
        
        try:
            # Phase 1: Validate instrument exists
            instrument = self.instruments.get_instrument(order.symbol)
            if not instrument:
                return self._create_rejection_execution(
                    order, "INVALID_INSTRUMENT", "Instrument not found in registry"
                )
            
            # Phase 2: Validate order parameters
            validation_error = self._validate_order(order, instrument)
            if validation_error:
                return self._create_rejection_execution(order, "VALIDATION_FAILED", validation_error)
            
            # Phase 3: Submit to broker
            execution = await self._execute_order_via_broker(order)
            
            # Phase 4: Track execution
            execution.latency_ms = (time.time() - start_time) * 1000
            self.execution_latencies.append(execution.latency_ms)
            
            # Log latency if it exceeds threshold
            if execution.latency_ms > self.config.max_order_submission_latency_ms:
                logger.warning(f"Order execution took {execution.latency_ms:.2f}ms (>{self.config.max_order_submission_latency_ms}ms threshold)")
            
            # Update state machine
            if execution.status != ExecutionStatus.REJECTED:
                self.orders[execution.order_id] = execution
                # Map ExecutionStatus to OrderStatus for state machine
                order_status = self._map_execution_to_order_status(execution.status)
                self.order_state_machine.transition(execution.order_id, order_status)
                
                if execution.status == ExecutionStatus.SUCCESS:
                    self.total_orders_filled += 1
            else:
                self.total_orders_rejected += 1
            
            logger.info(f"📊 Order {execution.order_id}: {execution.status.value} | Latency: {execution.latency_ms:.2f}ms")
            return execution
            
        except Exception as e:
            logger.error(f"❌ Order submission failed: {e}")
            latency = (time.time() - start_time) * 1000
            
            return StandardExecution(
                order_id=order.order_id,
                symbol=order.symbol,
                direction=order.direction,
                status=ExecutionStatus.FAILED,
                latency_ms=latency,
                broker=self.broker.name,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def _validate_order(self, order: StandardOrder, instrument) -> Optional[str]:
        """Validate order against instrument specifications."""
        # Validate quantity against lot size
        if order.volume < instrument.lot_size:
            return f"Quantity {order.volume} below minimum lot size {instrument.lot_size}"
        
        if order.volume % instrument.lot_size != 0:
            return f"Quantity {order.volume} not multiple of lot size {instrument.lot_size}"
        
        # Validate price against tick size (for non-market orders)
        if order.price > 0:
            tick_size = float(instrument.tick_size)
            price_remainder = order.price % tick_size
            
            if abs(price_remainder) > 0.001:  # Allow small floating point errors
                return f"Price {order.price} not multiple of tick size {tick_size}"
        
        # Additional validations can be added here
        return None
    
    async def _execute_order_via_broker(self, order: StandardOrder) -> StandardExecution:
        """Execute order through broker adapter."""
        try:
            # Submit to broker (this calls the Dhan adapter)
            execution = self.broker.place_order(order)
            
            # The Dhan adapter returns StandardExecution, but we need to ensure
            # it has the correct structure
            if not isinstance(execution, StandardExecution):
                # Convert if broker returns different format
                execution = StandardExecution(
                    order_id=order.order_id,
                    ticket=getattr(execution, 'ticket', 0),
                    symbol=order.symbol,
                    direction=order.direction,
                    fill_price=getattr(execution, 'fill_price', order.price),
                    fill_volume=getattr(execution, 'fill_volume', order.volume),
                    status=getattr(execution, 'status', ExecutionStatus.SUCCESS),
                    broker=self.broker.name,
                    timestamp=datetime.now()
                )
            
            return execution
            
        except Exception as e:
            logger.error(f"Broker execution error: {e}")
            return StandardExecution(
                order_id=order.order_id,
                symbol=order.symbol,
                direction=order.direction,
                status=ExecutionStatus.FAILED,
                broker=self.broker.name,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def _create_rejection_execution(
        self, 
        order: StandardOrder, 
        rejection_code: str, 
        rejection_reason: str
    ) -> StandardExecution:
        """Create a standardized rejection execution."""
        return StandardExecution(
            order_id=order.order_id,
            symbol=order.symbol,
            direction=order.direction,
            status=ExecutionStatus.REJECTED,
            broker=self.broker.name,
            timestamp=datetime.now(),
            error=f"{rejection_code}: {rejection_reason}"
        )
    
    def _map_execution_to_order_status(self, execution_status: ExecutionStatus) -> OrderStatus:
        """Map ExecutionStatus to OrderStatus for state machine."""
        mapping = {
            ExecutionStatus.SUCCESS: OrderStatus.FILLED,
            ExecutionStatus.PARTIAL: OrderStatus.PARTIALLY_FILLED,
            ExecutionStatus.FAILED: OrderStatus.ERROR,
            ExecutionStatus.REJECTED: OrderStatus.REJECTED,
            ExecutionStatus.TIMEOUT: OrderStatus.ERROR
        }
        return mapping.get(execution_status, OrderStatus.ERROR)
    
    async def modify_order(
        self,
        order_id: str,
        new_price: Optional[float] = None,
        new_quantity: Optional[int] = None
    ) -> StandardExecution:
        """Modify pending order."""
        if order_id not in self.orders:
            return self._create_error_execution(order_id, "ORDER_NOT_FOUND", "Order not found in registry")
        
        current_order = self.orders[order_id]
        current_state = self.order_state_machine.get_state(order_id)
        
        # Can only modify pending/open orders
        if current_state not in [OrderStatus.PENDING, OrderStatus.OPEN]:
            return self._create_error_execution(
                order_id, "ORDER_NOT_MODIFIABLE", 
                f"Cannot modify order in {current_state.value} state"
            )
        
        try:
            # Call broker modification method
            success = self.broker.modify_order(order_id, price=new_price, quantity=new_quantity)
            
            if success:
                # Update local tracking
                if new_price is not None:
                    current_order.fill_price = new_price
                if new_quantity is not None:
                    current_order.fill_volume = new_quantity
                
                return StandardExecution(
                    execution_id=f"MOD_{int(time.time() * 1000)}",
                    order_id=order_id,
                    symbol=current_order.symbol,
                    direction=current_order.direction,
                    status=ExecutionStatus.SUCCESS,
                    broker=self.broker.name,
                    timestamp=datetime.now()
                )
            else:
                return self._create_error_execution(order_id, "MODIFICATION_FAILED", "Broker rejected modification")
                
        except Exception as e:
            logger.error(f"Error modifying order {order_id}: {e}")
            return self._create_error_execution(order_id, "MODIFICATION_ERROR", str(e))
    
    async def cancel_order(self, order_id: str) -> StandardExecution:
        """Cancel pending order."""
        if order_id not in self.orders:
            return self._create_error_execution(order_id, "ORDER_NOT_FOUND", "Order not found in registry")
        
        current_order = self.orders[order_id]
        current_state = self.order_state_machine.get_state(order_id)
        
        # Can only cancel pending/open orders
        if current_state not in [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
            return self._create_error_execution(
                order_id, "ORDER_NOT_CANCELLABLE",
                f"Cannot cancel order in {current_state.value} state"
            )
        
        try:
            # Call broker cancellation method
            success = self.broker.cancel_order(order_id)
            
            if success:
                # Update state machine
                self.order_state_machine.transition(order_id, OrderStatus.CANCELLED)
                
                return StandardExecution(
                    execution_id=f"CAN_{int(time.time() * 1000)}",
                    order_id=order_id,
                    symbol=current_order.symbol,
                    direction=current_order.direction,
                    status=ExecutionStatus.SUCCESS,
                    broker=self.broker.name,
                    timestamp=datetime.now()
                )
            else:
                return self._create_error_execution(order_id, "CANCELLATION_FAILED", "Broker rejected cancellation")
                
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return self._create_error_execution(order_id, "CANCELLATION_ERROR", str(e))
    
    def _create_error_execution(self, order_id: str, error_code: str, error_message: str) -> StandardExecution:
        """Create a standardized error execution."""
        return StandardExecution(
            execution_id=f"ERR_{int(time.time() * 1000)}",
            order_id=order_id,
            symbol="UNKNOWN",
            direction="LONG",
            status=ExecutionStatus.FAILED,
            broker=self.broker.name,
            timestamp=datetime.now(),
            error=f"{error_code}: {error_message}"
        )
    
    def get_pending_orders(self) -> List[StandardExecution]:
        """Return all pending orders."""
        return [
            order for order in self.orders.values()
            if self.order_state_machine.get_state(order.order_id) in [
                OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED
            ]
        ]
    
    def get_order_by_id(self, order_id: str) -> Optional[StandardExecution]:
        """Get order by ID."""
        return self.orders.get(order_id)
    
    def get_orders_by_symbol(self, symbol: str) -> List[StandardExecution]:
        """Get all orders for a specific symbol."""
        return [order for order in self.orders.values() if order.symbol == symbol]
    
    def get_order_statistics(self) -> Dict:
        """Get order execution statistics."""
        avg_latency = sum(self.execution_latencies) / len(self.execution_latencies) if self.execution_latencies else 0
        
        return {
            "total_orders_submitted": self.total_orders_submitted,
            "total_orders_filled": self.total_orders_filled,
            "total_orders_rejected": self.total_orders_rejected,
            "fill_rate": (self.total_orders_filled / self.total_orders_submitted * 100) if self.total_orders_submitted > 0 else 0,
            "rejection_rate": (self.total_orders_rejected / self.total_orders_submitted * 100) if self.total_orders_submitted > 0 else 0,
            "avg_execution_latency_ms": avg_latency,
            "total_tracked_orders": len(self.orders),
            "pending_orders": len(self.get_pending_orders())
        }