"""
╔══════════════════════════════════════════════════════════════╗
║       MARKET ABSTRACTION LAYER — EXECUTION PIPELINE         ║
║  Centralized order execution flow for all asset classes      ║
╚══════════════════════════════════════════════════════════════╝

Pipeline stages:
  Signal → Risk Validation → Capital Allocation → Broker Selection
    → Execution → Confirmation → Trade Journal → Analytics → Learning

This pipeline is reusable across Forex, Indian Market, and Crypto.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from zohra.config.settings import DEFAULT_BROKER
from zohra.security.permissions import TradingPermissionGateway, trading_permission_gateway

logger = logging.getLogger("zohra.pipeline")


# ════════════════════════════════════════════════════════════════
#  Pipeline Stage Enum
# ════════════════════════════════════════════════════════════════

class PipelineStage(str, Enum):
    SIGNAL = "SIGNAL"
    RISK_VALIDATION = "RISK_VALIDATION"
    CAPITAL_ALLOCATION = "CAPITAL_ALLOCATION"
    BROKER_SELECTION = "BROKER_SELECTION"
    PERMISSION_APPROVAL = "PERMISSION_APPROVAL"
    EXECUTION = "EXECUTION"
    CONFIRMATION = "CONFIRMATION"
    JOURNALING = "JOURNALING"
    ANALYTICS = "ANALYTICS"
    LEARNING = "LEARNING"


class PipelineStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


# ════════════════════════════════════════════════════════════════
#  Pipeline Context
# ════════════════════════════════════════════════════════════════

@dataclass
class PipelineContext:
    """
    Carries data through all pipeline stages.
    Each stage reads from and writes to this context.
    """
    # ── Signal data ──
    signal_id: str = ""
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence_score: float = 0.0
    strategy: str = ""
    asset_class: str = "forex"

    # ── Risk validation ──
    risk_approved: bool = False
    risk_reason: str = ""
    risk_grade: str = ""

    # ── Capital allocation ──
    position_size_lots: float = 0.0
    risk_usd: float = 0.0
    risk_pct: float = 0.0

    # ── Broker selection ──
    broker: str = ""
    broker_fallback: str = ""

    # -- Permission approval --
    permission_approved: bool = False
    permission_reason: str = ""
    permission_tier: int = 0

    # ── Execution ──
    ticket: int = 0
    fill_price: float = 0.0
    fill_volume: float = 0.0
    execution_latency_ms: float = 0.0
    execution_status: str = ""
    execution_error: Optional[str] = None

    # ── Confirmation ──
    trade_id: str = ""
    confirmed: bool = False

    # ── State tracking ──
    current_stage: PipelineStage = PipelineStage.SIGNAL
    status: PipelineStatus = PipelineStatus.PENDING
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    stage_results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence_score": self.confidence_score,
            "strategy": self.strategy,
            "asset_class": self.asset_class,
            "risk_approved": self.risk_approved,
            "risk_grade": self.risk_grade,
            "position_size_lots": self.position_size_lots,
            "broker": self.broker,
            "permission_approved": self.permission_approved,
            "permission_reason": self.permission_reason,
            "ticket": self.ticket,
            "fill_price": self.fill_price,
            "execution_status": self.execution_status,
            "trade_id": self.trade_id,
            "status": self.status.value,
            "current_stage": self.current_stage.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "errors": self.errors,
        }


# ════════════════════════════════════════════════════════════════
#  Pipeline Step (Pluggable stage handler)
# ════════════════════════════════════════════════════════════════

class PipelineStep:
    """
    Base class for a pipeline stage handler.
    Override execute() to implement stage-specific logic.
    """

    def __init__(self, stage: PipelineStage, name: str = ""):
        self.stage = stage
        self.name = name or stage.value

    def execute(self, context: PipelineContext) -> PipelineContext:
        """
        Execute this pipeline stage.
        Must update context and return it.
        Raise an exception to abort the pipeline.
        """
        return context

    def should_skip(self, context: PipelineContext) -> bool:
        """
        Return True to skip this stage.
        Default: never skip.
        """
        return False


# ════════════════════════════════════════════════════════════════
#  Built-in Pipeline Steps
# ════════════════════════════════════════════════════════════════

class SignalValidationStep(PipelineStep):
    """Validates the incoming signal has all required fields."""

    def __init__(self):
        super().__init__(PipelineStage.SIGNAL, "SignalValidation")

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.symbol:
            raise ValueError("Signal missing symbol")
        if not context.direction:
            raise ValueError("Signal missing direction")
        if context.stop_loss <= 0:
            raise ValueError("Signal missing stop_loss")
        if context.take_profit <= 0:
            raise ValueError("Signal missing take_profit")

        context.stage_results["signal"] = {
            "symbol": context.symbol,
            "direction": context.direction,
            "score": context.confidence_score,
            "valid": True,
        }
        return context


class RiskValidationStep(PipelineStep):
    """Runs risk checks via a provided risk evaluator."""

    def __init__(self, risk_evaluator: Callable = None):
        super().__init__(PipelineStage.RISK_VALIDATION, "RiskValidation")
        self._evaluator = risk_evaluator

    def execute(self, context: PipelineContext) -> PipelineContext:
        if self._evaluator:
            result = self._evaluator(context)
            context.risk_approved = result.get("approved", False)
            context.risk_reason = result.get("reason", "")
            context.risk_grade = result.get("grade", "")
            context.position_size_lots = result.get("lots", 0.0)
            context.risk_usd = result.get("risk_usd", 0.0)
        else:
            context.risk_approved = False
            context.risk_reason = "No risk evaluator configured"

        if not context.risk_approved:
            context.status = PipelineStatus.REJECTED
            raise ValueError(f"Risk rejected: {context.risk_reason}")

        context.stage_results["risk"] = {
            "approved": context.risk_approved,
            "grade": context.risk_grade,
            "lots": context.position_size_lots,
        }
        return context


class CapitalAllocationStep(PipelineStep):
    """Allocates capital based on risk grade and equity."""

    def __init__(self, allocator: Callable = None):
        super().__init__(PipelineStage.CAPITAL_ALLOCATION, "CapitalAllocation")
        self._allocator = allocator

    def execute(self, context: PipelineContext) -> PipelineContext:
        if self._allocator:
            alloc = self._allocator(context)
            context.position_size_lots = alloc.get("lots", context.position_size_lots)
            context.risk_usd = alloc.get("risk_usd", context.risk_usd)

        context.stage_results["allocation"] = {
            "lots": context.position_size_lots,
            "risk_usd": context.risk_usd,
        }
        return context


class BrokerSelectionStep(PipelineStep):
    """Selects the appropriate broker for this trade."""

    def __init__(self, selector: Callable = None, default_broker: str = "mt5"):
        super().__init__(PipelineStage.BROKER_SELECTION, "BrokerSelection")
        self._selector = selector
        self._default = default_broker

    def execute(self, context: PipelineContext) -> PipelineContext:
        if self._selector:
            selected = self._selector(context)
            context.broker = selected.get("broker", self._default)
            context.broker_fallback = selected.get("fallback", "")
        else:
            context.broker = context.broker or self._default

        context.stage_results["broker_selection"] = {
            "broker": context.broker,
            "fallback": context.broker_fallback,
        }
        return context


class PermissionApprovalStep(PipelineStep):
    """Requires Tier 4 permission before any broker order is sent."""

    def __init__(self, gateway: TradingPermissionGateway = None):
        super().__init__(PipelineStage.PERMISSION_APPROVAL, "PermissionApproval")
        self._gateway = gateway or trading_permission_gateway

    def execute(self, context: PipelineContext) -> PipelineContext:
        decision = self._gateway.authorize_trade_execution({
            "symbol": context.symbol,
            "direction": context.direction,
            "lots": context.position_size_lots,
            "broker": context.broker or DEFAULT_BROKER,
            "risk_approved": context.risk_approved,
            "consensus_status": context.metadata.get("consensus_status", "APPROVED"),
            "authorization_token": context.metadata.get("authorization_token", ""),
        })
        context.permission_approved = decision.approved
        context.permission_reason = decision.reason
        context.permission_tier = int(decision.tier)
        context.stage_results["permission"] = decision.to_dict()

        if not decision.approved:
            context.status = PipelineStatus.REJECTED
            raise PermissionError(decision.reason)

        return context


class ExecutionStep(PipelineStep):
    """Executes the trade via the BrokerManager."""

    def __init__(self, executor: Callable = None):
        super().__init__(PipelineStage.EXECUTION, "Execution")
        self._executor = executor

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.permission_approved:
            raise PermissionError("Tier 4 permission approval is required before execution.")

        start = time.perf_counter()

        if self._executor:
            result = self._executor(context)
        else:
            # Default: use broker_manager
            from zohra.brokers.manager import broker_manager
            result = broker_manager.open_trade(
                symbol=context.symbol,
                direction=context.direction,
                lots=context.position_size_lots,
                stop_loss=context.stop_loss,
                take_profit=context.take_profit,
                broker=context.broker if context.broker else None,
            )

        elapsed = (time.perf_counter() - start) * 1000
        context.execution_latency_ms = elapsed

        if result and result.get("ticket"):
            context.ticket = result["ticket"]
            context.fill_price = result.get("price", result.get("fill_price", 0.0))
            context.fill_volume = result.get("lots", result.get("fill_volume", 0.0))
            context.execution_status = "SUCCESS"
            context.confirmed = True
        else:
            context.execution_status = "FAILED"
            context.execution_error = str(result) if result else "No response"
            raise RuntimeError(f"Execution failed: {context.execution_error}")

        context.stage_results["execution"] = {
            "ticket": context.ticket,
            "fill_price": context.fill_price,
            "latency_ms": round(elapsed, 2),
        }
        return context


class ConfirmationStep(PipelineStep):
    """Confirms the execution and generates trade_id."""

    def __init__(self):
        super().__init__(PipelineStage.CONFIRMATION, "Confirmation")

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.trade_id:
            context.trade_id = (
                f"MAL_{context.symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            )
        context.confirmed = True
        context.stage_results["confirmation"] = {
            "trade_id": context.trade_id,
            "confirmed": True,
        }
        return context


class JournalingStep(PipelineStep):
    """Logs the trade to the journal/database."""

    def __init__(self, journal_callback: Callable = None):
        super().__init__(PipelineStage.JOURNALING, "Journaling")
        self._callback = journal_callback

    def execute(self, context: PipelineContext) -> PipelineContext:
        if self._callback:
            try:
                self._callback(context)
            except Exception as e:
                logger.error(f"Journaling error: {e}")
                context.errors.append(f"Journaling: {e}")
        context.stage_results["journaling"] = {"logged": True}
        return context


class AnalyticsStep(PipelineStep):
    """Emits analytics events."""

    def __init__(self, analytics_callback: Callable = None):
        super().__init__(PipelineStage.ANALYTICS, "Analytics")
        self._callback = analytics_callback

    def execute(self, context: PipelineContext) -> PipelineContext:
        if self._callback:
            try:
                self._callback(context)
            except Exception as e:
                logger.error(f"Analytics error: {e}")
                context.errors.append(f"Analytics: {e}")
        context.stage_results["analytics"] = {"emitted": True}
        return context


class LearningStep(PipelineStep):
    """Feeds the trade into the learning engine."""

    def __init__(self, learning_callback: Callable = None):
        super().__init__(PipelineStage.LEARNING, "Learning")
        self._callback = learning_callback

    def execute(self, context: PipelineContext) -> PipelineContext:
        if self._callback:
            try:
                self._callback(context)
            except Exception as e:
                logger.error(f"Learning engine error: {e}")
                context.errors.append(f"Learning: {e}")
        context.stage_results["learning"] = {"processed": True}
        return context


# ════════════════════════════════════════════════════════════════
#  Execution Pipeline
# ════════════════════════════════════════════════════════════════

class ExecutionPipeline:
    """
    Orchestrates the full order execution flow.

    Usage:
        pipeline = ExecutionPipeline()
        pipeline.add_step(SignalValidationStep())
        pipeline.add_step(RiskValidationStep(my_risk_evaluator))
        pipeline.add_step(ExecutionStep())
        pipeline.add_step(ConfirmationStep())

        context = PipelineContext(symbol="EURUSD", direction="LONG", ...)
        result = pipeline.run(context)
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._steps: List[PipelineStep] = []
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []
        self._error_hooks: List[Callable] = []

    def add_step(self, step: PipelineStep) -> ExecutionPipeline:
        """Add a pipeline step. Returns self for chaining."""
        self._steps.append(step)
        return self

    def add_pre_hook(self, hook: Callable) -> ExecutionPipeline:
        """Add a pre-execution hook. Called before the pipeline runs."""
        self._pre_hooks.append(hook)
        return self

    def add_post_hook(self, hook: Callable) -> ExecutionPipeline:
        """Add a post-execution hook. Called after successful completion."""
        self._post_hooks.append(hook)
        return self

    def add_error_hook(self, hook: Callable) -> ExecutionPipeline:
        """Add an error hook. Called when the pipeline fails."""
        self._error_hooks.append(hook)
        return self

    def run(self, context: PipelineContext) -> PipelineContext:
        """
        Execute the full pipeline.
        Each stage updates the context.
        Pipeline stops on first failure (except post-execution stages like journaling).
        """
        context.status = PipelineStatus.RUNNING
        context.started_at = datetime.utcnow()

        # Pre-hooks
        for hook in self._pre_hooks:
            try:
                hook(context)
            except Exception as e:
                logger.error(f"Pre-hook error: {e}")

        logger.info(
            f"[Pipeline:{self.name}] Starting execution for "
            f"{context.symbol} {context.direction}"
        )

        try:
            for step in self._steps:
                # Check if step should be skipped
                if step.should_skip(context):
                    logger.debug(f"[Pipeline:{self.name}] Skipping stage: {step.name}")
                    context.stage_results[step.stage.value] = {"skipped": True}
                    continue

                context.current_stage = step.stage
                logger.debug(f"[Pipeline:{self.name}] Executing stage: {step.name}")

                try:
                    context = step.execute(context)
                except Exception as e:
                    context.errors.append(f"{step.name}: {str(e)}")

                    # Post-execution stages (journaling, analytics, learning)
                    # should not abort the pipeline
                    if step.stage in (
                        PipelineStage.JOURNALING,
                        PipelineStage.ANALYTICS,
                        PipelineStage.LEARNING,
                    ):
                        logger.warning(
                            f"[Pipeline:{self.name}] Non-critical stage "
                            f"{step.name} failed: {e}"
                        )
                        continue
                    else:
                        raise

            # Success
            context.status = PipelineStatus.COMPLETED
            context.completed_at = datetime.utcnow()

            logger.info(
                f"[Pipeline:{self.name}] ✅ Completed: {context.symbol} "
                f"{context.direction} | Ticket={context.ticket} | "
                f"Latency={context.execution_latency_ms:.1f}ms"
            )

            # Post-hooks
            for hook in self._post_hooks:
                try:
                    hook(context)
                except Exception as e:
                    logger.error(f"Post-hook error: {e}")

        except Exception as e:
            context.status = PipelineStatus.FAILED
            context.completed_at = datetime.utcnow()
            context.execution_error = str(e)

            logger.error(
                f"[Pipeline:{self.name}] ❌ Failed at {context.current_stage.value}: {e}"
            )

            # Error hooks
            for hook in self._error_hooks:
                try:
                    hook(context, e)
                except Exception as he:
                    logger.error(f"Error hook error: {he}")

        return context


# ════════════════════════════════════════════════════════════════
#  Factory: Default Pipeline
# ════════════════════════════════════════════════════════════════

def create_default_pipeline(
    risk_evaluator: Callable = None,
    capital_allocator: Callable = None,
    broker_selector: Callable = None,
    permission_gateway: TradingPermissionGateway = None,
    executor: Callable = None,
    journal_callback: Callable = None,
    analytics_callback: Callable = None,
    learning_callback: Callable = None,
    default_broker: str = "mt5",
) -> ExecutionPipeline:
    """
    Create a default execution pipeline with all standard stages.
    Pass custom callables to override stage behavior.
    """
    pipeline = ExecutionPipeline("default")
    pipeline.add_step(SignalValidationStep())
    pipeline.add_step(RiskValidationStep(risk_evaluator))
    pipeline.add_step(CapitalAllocationStep(capital_allocator))
    pipeline.add_step(BrokerSelectionStep(broker_selector, default_broker))
    pipeline.add_step(PermissionApprovalStep(permission_gateway))
    pipeline.add_step(ExecutionStep(executor))
    pipeline.add_step(ConfirmationStep())
    pipeline.add_step(JournalingStep(journal_callback))
    pipeline.add_step(AnalyticsStep(analytics_callback))
    pipeline.add_step(LearningStep(learning_callback))
    return pipeline
