"""
╔══════════════════════════════════════════════════════════════╗
║                 INDIAN MARKET ENGINE - MAIN                  ║
║  NSE/BSE Trading Engine with AI Integration & Risk Management ║
╚══════════════════════════════════════════════════════════════╝

The Indian Market Engine provides comprehensive access to NSE and BSE markets
through the Dhan adapter. It supports:
- Multi-asset trading (Equity, Futures, Options)
- Real-time streaming data processing
- AI-driven decision making with veto authority
- Risk management integration
- Portfolio tracking and P&L calculation
- Integration with all ZOHRA divisions

Architecture Components:
- Engine Coordinator: Main orchestrator and public API
- Connection Manager: Dhan API connectivity with resilience
- Session Manager: Market session state tracking
- Instrument Registry: Fast instrument specification lookup
- Data Stream Processor: WebSocket tick processing
- Order Manager: Order validation and execution
- Position Manager: Position tracking with real-time P&L
- Event Publisher: Internal event communication
- Integration Bridge: ZOHRA divisions integration
"""

import asyncio
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from .components.connection_manager import ConnectionManager
from .components.session_manager import SessionManager
from .components.instrument_registry import InstrumentRegistry
from .components.data_stream_processor import DataStreamProcessor
from .components.order_manager import OrderManager
from .components.position_manager import PositionManager
from .components.event_publisher import EventPublisher
from .components.integration_bridge import IntegrationBridge
from .config import EngineConfig
from .models import TradeSetup, AIEvaluation, AIDecision, HealthStatus
from ..brokers.manager import BrokerManager
from ..brokers.models import StandardOrder, StandardExecution, StandardPosition, OrderStatus

logger = logging.getLogger(__name__)


class IndianMarketEngine:
    """
    Main coordinator for Indian Market Engine operations.
    Integrates with ZOHRA Trading Core through standardized interface.
    
    This is the primary entry point for all Indian market trading operations,
    providing a unified interface that abstracts the complexity of multi-component
    coordination while maintaining high performance and reliability.
    """
    
    def __init__(
        self,
        config: EngineConfig,
        broker_manager: BrokerManager,
        integration_bridge: IntegrationBridge
    ):
        """
        Initialize the Indian Market Engine with all subsystems.
        
        Args:
            config: Engine configuration with all parameters
            broker_manager: MAL broker manager for Dhan adapter access
            integration_bridge: Integration layer for ZOHRA divisions
        """
        self.config = config
        self.broker = broker_manager.get_adapter("dhan")
        self.integration = integration_bridge
        
        # Initialize subsystems
        self.connection_mgr = ConnectionManager(self.broker, config)
        self.session_mgr = SessionManager(self.broker, config)
        self.instrument_registry = InstrumentRegistry(self.broker, config)
        self.data_processor = DataStreamProcessor(self.broker, config)
        self.order_mgr = OrderManager(self.broker, self.instrument_registry, config)
        self.position_mgr = PositionManager(self.broker, config)
        self.event_publisher = EventPublisher()
        
        # State tracking
        self.is_running = False
        self.health_status = HealthStatus.UNKNOWN
        self._startup_time: Optional[datetime] = None
        
        # Setup event subscriptions
        self._setup_event_subscriptions()
        
        logger.info("Indian Market Engine initialized")
    
    def _setup_event_subscriptions(self) -> None:
        """Setup internal event subscriptions between components."""
        # Session manager broadcasts to all components
        self.session_mgr.subscribe_transitions(self._on_session_transition)
        
        # Data processor sends ticks to position manager
        self.data_processor.register_tick_handler(self.position_mgr.update_position_price)
        
        # Position manager notifies integration bridge
        self.position_mgr.register_position_opened_handler(self.integration.notify_position_opened)
        self.position_mgr.register_position_closed_handler(self.integration.notify_position_closed)
    
    async def start(self) -> None:
        """
        Initialize and start all subsystems in correct order.
        
        This follows a carefully orchestrated startup sequence to ensure
        all dependencies are satisfied before beginning operations.
        """
        logger.info("Starting Indian Market Engine")
        self._startup_time = datetime.now()
        
        try:
            # Phase 1: Establish connection
            logger.info("Phase 1: Establishing Dhan API connection...")
            connected = await self.connection_mgr.connect()
            if not connected:
                raise RuntimeError("Failed to connect to Dhan API")
            
            # Phase 2: Load instruments
            logger.info("Phase 2: Loading instrument specifications...")
            await self.instrument_registry.initialize()
            
            # Phase 3: Initialize session tracking
            logger.info("Phase 3: Initializing market session tracking...")
            await self.session_mgr.initialize()
            
            # Phase 4: Start data streaming
            logger.info("Phase 4: Starting real-time data streaming...")
            await self.data_processor.start()
            
            # Phase 5: Start background loops
            logger.info("Phase 5: Starting monitoring loops...")
            asyncio.create_task(self._health_monitor_loop())
            asyncio.create_task(self._position_update_loop())
            asyncio.create_task(self._sl_tp_monitor_loop())
            
            self.is_running = True
            self.health_status = HealthStatus.HEALTHY
            
            startup_duration = (datetime.now() - self._startup_time).total_seconds()
            logger.info(f"✅ Indian Market Engine started successfully in {startup_duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Failed to start Indian Market Engine: {e}")
            self.health_status = HealthStatus.UNHEALTHY
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """
        Gracefully shutdown all subsystems in reverse order.
        
        Ensures all positions are properly closed if configured for intraday mode
        and all resources are cleaned up properly.
        """
        logger.info("Stopping Indian Market Engine")
        self.is_running = False
        
        try:
            # Stop accepting new trades
            self.health_status = HealthStatus.STOPPING
            
            # Stop data streaming first
            await self.data_processor.stop()
            
            # Close positions if configured for intraday
            if self.config.intraday_mode:
                logger.info("Closing all positions (intraday mode)")
                await self._close_all_positions()
            
            # Cancel any pending orders
            await self._cancel_all_pending_orders()
            
            # Disconnect from Dhan
            await self.connection_mgr.disconnect()
            
            self.health_status = HealthStatus.STOPPED
            logger.info("✅ Indian Market Engine stopped gracefully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            self.health_status = HealthStatus.UNHEALTHY
    
    async def submit_trade_setup(self, setup: TradeSetup) -> Optional[StandardExecution]:
        """
        Submit a trade setup for AI evaluation and potential execution.
        
        This is the main entry point for trade execution. It coordinates:
        1. AI evaluation with veto authority
        2. Capital allocation request
        3. Risk validation 
        4. Order execution through Dhan adapter
        
        Args:
            setup: Complete trade setup with entry/exit criteria
            
        Returns:
            StandardExecution if trade is executed, None if rejected/deferred
        """
        if not self.is_running:
            logger.warning(f"Engine not running, rejecting setup {setup.setup_id}")
            return None
        
        if self.health_status != HealthStatus.HEALTHY:
            logger.warning(f"Engine unhealthy, rejecting setup {setup.setup_id}")
            return None
        
        logger.info(f"Processing trade setup {setup.setup_id} for {setup.symbol}")
        
        try:
            # Phase 1: AI Evaluation
            logger.debug(f"Submitting setup {setup.setup_id} to AI for evaluation")
            ai_eval = await self.integration.evaluate_trade_setup(setup)
            
            if ai_eval.decision == AIDecision.REJECT:
                logger.info(f"❌ Trade setup {setup.setup_id} rejected by AI: {ai_eval.reasoning}")
                await self.integration.log_rejected_setup(setup, ai_eval)
                return None
                
            elif ai_eval.decision == AIDecision.DEFER:
                logger.info(f"⏸️ Trade setup {setup.setup_id} deferred for re-evaluation")
                await self._queue_deferred_setup(setup)
                return None
            
            logger.info(f"✅ Trade setup {setup.setup_id} approved by AI (score: {ai_eval.decision_score:.2f})")
            
            # Phase 2: Create order from setup
            order = self._create_order_from_setup(setup)
            
            # Phase 3: Capital allocation
            capital_required = self._calculate_capital_required(order, setup)
            logger.debug(f"Requesting {capital_required} capital allocation")
            
            capital_ok = await self.integration.request_capital(capital_required)
            if not capital_ok:
                logger.warning(f"❌ Insufficient capital for setup {setup.setup_id}")
                return StandardExecution(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    direction=order.direction,
                    status=ExecutionStatus.REJECTED,
                    error="INSUFFICIENT_CAPITAL",
                    broker=self.broker.name,
                    timestamp=datetime.now()
                )
            
            # Phase 4: Risk validation
            logger.debug(f"Validating setup {setup.setup_id} against risk limits")
            risk_ok = await self.integration.validate_risk(order, self.position_mgr.get_all_positions())
            
            if not risk_ok:
                logger.warning(f"❌ Order failed risk validation for setup {setup.setup_id}")
                await self.integration.release_capital(capital_required)
                return StandardExecution(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    direction=order.direction,
                    status=ExecutionStatus.REJECTED,
                    error="RISK_LIMIT_EXCEEDED",
                    broker=self.broker.name,
                    timestamp=datetime.now()
                )
            
            # Phase 5: Execute order
            logger.info(f"🚀 Executing order for setup {setup.setup_id}")
            execution = await self.order_mgr.submit_order(order)
            
            # Phase 6: Record AI decision in execution metadata
            if execution.status != ExecutionStatus.REJECTED:
                execution.raw_response['ai_decision_score'] = ai_eval.decision_score
                execution.raw_response['ai_reasoning'] = ai_eval.reasoning
                execution.raw_response['setup_id'] = setup.setup_id
                
                logger.info(f"✅ Trade executed: {execution.ticket} | {setup.symbol} | {execution.fill_price}")
            
            return execution
            
        except Exception as e:
            logger.error(f"Error processing setup {setup.setup_id}: {e}")
            # Release capital on error
            try:
                await self.integration.release_capital(capital_required)
            except:
                pass
            return None
    
    async def get_positions(
        self,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None
    ) -> List[StandardPosition]:
        """Query open positions with optional filtering."""
        return self.position_mgr.query_positions(symbol=symbol, asset_class=asset_class)
    
    async def close_position(
        self,
        ticket: str,
        order_type: str = "MARKET",
        price: Optional[Decimal] = None
    ) -> StandardExecution:
        """Close an open position."""
        position = self.position_mgr.get_position(ticket)
        if not position:
            raise ValueError(f"Position {ticket} not found")
        
        logger.info(f"Closing position {ticket} for {position['symbol']}")
        
        # Create closing order (opposite side)
        close_side = "SELL" if position['direction'] == "LONG" else "BUY"
        
        close_order = StandardOrder(
            symbol=position['symbol'],
            side=close_side,
            order_type=order_type,
            volume=position['volume'],
            price=price or 0.0,
            comment=f"Close position {ticket}"
        )
        
        return await self.order_mgr.submit_order(close_order)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Return current health status of all subsystems."""
        return {
            "engine_status": "RUNNING" if self.is_running else "STOPPED",
            "health_status": self.health_status.value,
            "startup_time": self._startup_time.isoformat() if self._startup_time else None,
            "uptime_seconds": int((datetime.now() - self._startup_time).total_seconds()) if self._startup_time else 0,
            "connection_status": self.connection_mgr.get_status(),
            "data_stream_status": self.data_processor.get_status(),
            "session": self.session_mgr.current_session.value if hasattr(self.session_mgr, 'current_session') else "UNKNOWN",
            "instruments_loaded": len(self.instrument_registry.instruments),
            "active_positions": len(self.position_mgr.get_all_positions()),
            "pending_orders": len(self.order_mgr.get_pending_orders())
        }
    
    # ─── Private Helper Methods ────────────────────────────
    
    def _create_order_from_setup(self, setup: TradeSetup) -> StandardOrder:
        """Convert trade setup to standardized order."""
        return StandardOrder(
            symbol=setup.symbol,
            side=setup.side,
            order_type="LIMIT" if setup.suggested_entry else "MARKET",
            volume=setup.suggested_quantity,
            price=setup.suggested_entry,
            stop_loss=setup.suggested_stop_loss,
            take_profit=setup.suggested_take_profit,
            comment=f"Setup {setup.setup_id}"
        )
    
    def _calculate_capital_required(self, order: StandardOrder, setup: TradeSetup) -> Decimal:
        """Calculate capital required for the order."""
        # Basic calculation - can be enhanced based on margin requirements
        return Decimal(str(order.volume * order.price)) if order.price > 0 else Decimal("10000")
    
    async def _queue_deferred_setup(self, setup: TradeSetup) -> None:
        """Queue setup for re-evaluation after delay."""
        # Implementation depends on scheduling system
        logger.info(f"Queueing deferred setup {setup.setup_id} for re-evaluation")
    
    async def _close_all_positions(self) -> None:
        """Close all open positions (used for intraday mode)."""
        positions = self.position_mgr.get_all_positions()
        logger.info(f"Closing {len(positions)} open positions")
        
        for position in positions:
            try:
                await self.close_position(str(position.get('ticket', position.get('position_id', ''))))
            except Exception as e:
                logger.error(f"Error closing position {position}: {e}")
    
    async def _cancel_all_pending_orders(self) -> None:
        """Cancel all pending orders."""
        pending_orders = self.order_mgr.get_pending_orders()
        logger.info(f"Cancelling {len(pending_orders)} pending orders")
        
        for order in pending_orders:
            try:
                await self.order_mgr.cancel_order(order.order_id)
            except Exception as e:
                logger.error(f"Error cancelling order {order.order_id}: {e}")
    
    async def _on_session_transition(self, transition) -> None:
        """Handle market session transitions."""
        logger.info(f"Market session transition: {transition.previous_session} → {transition.current_session}")
        
        # Broadcast to integration bridge
        await self.integration.broadcast_session_transition(transition)
        
        # Handle session-specific actions
        if transition.current_session.value == "CLOSED" and self.config.intraday_mode:
            logger.info("Market closed - closing all positions (intraday mode)")
            await self._close_all_positions()
    
    async def _health_monitor_loop(self) -> None:
        """Monitor system health and component status."""
        while self.is_running:
            try:
                await asyncio.sleep(30)  # Health check every 30 seconds
                
                # Check connection health
                if not self.connection_mgr.is_connected():
                    logger.warning("Connection manager reports disconnected")
                    self.health_status = HealthStatus.DEGRADED
                
                # Check data stream health
                if not self.data_processor.is_healthy():
                    logger.warning("Data stream processor unhealthy")
                    self.health_status = HealthStatus.DEGRADED
                
                # If all checks pass, restore healthy status
                if (self.connection_mgr.is_connected() and 
                    self.data_processor.is_healthy() and 
                    self.health_status == HealthStatus.DEGRADED):
                    self.health_status = HealthStatus.HEALTHY
                    logger.info("System health restored")
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
    
    async def _position_update_loop(self) -> None:
        """Periodic position synchronization with broker."""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Sync every minute
                await self.position_mgr.sync_positions()
                
            except Exception as e:
                logger.error(f"Position update loop error: {e}")
    
    async def _sl_tp_monitor_loop(self) -> None:
        """Monitor stop loss and take profit triggers."""
        while self.is_running:
            try:
                await asyncio.sleep(1)  # Check every second
                
                triggered_tickets = await self.position_mgr.check_sl_tp_triggers()
                
                for ticket in triggered_tickets:
                    try:
                        await self.close_position(ticket)
                        logger.info(f"SL/TP triggered - closed position {ticket}")
                    except Exception as e:
                        logger.error(f"Error closing triggered position {ticket}: {e}")
                
            except Exception as e:
                logger.error(f"SL/TP monitor error: {e}")