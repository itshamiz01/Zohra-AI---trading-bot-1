"""
Structured logging infrastructure with JSONL format for audit compliance.
"""

import gzip
import json
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict

# Optional structlog support
try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


class CompressingTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Log handler with automatic compression of rotated log files."""
    
    def __init__(self, filename: str, when: str = 'midnight', 
                 interval: int = 1, backupCount: int = 90):
        super().__init__(filename, when, interval, backupCount)
    
    def doRollover(self):
        """Rollover and compress old log file."""
        super().doRollover()
        
        # Find rotated log file and compress it
        log_dir = Path(self.baseFilename).parent
        for log_file in log_dir.glob("*.log.*"):
            if log_file.suffix not in ['.gz']:
                # Compress log file
                with open(log_file, 'rb') as f_in:
                    with gzip.open(f"{log_file}.gz", 'wb') as f_out:
                        f_out.writelines(f_in)
                
                # Delete uncompressed file
                os.remove(log_file)


def setup_logging(config):
    """
    Configure structured logging with JSONL format.
    
    Args:
        config: EngineConfig instance with log settings
    
    Returns:
        Configured logger (structlog if available, otherwise standard logger)
    """
    # Ensure log directory exists
    log_dir = Path(config.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, config.log_level.upper()),
        handlers=[
            CompressingTimedRotatingFileHandler(
                filename=config.log_file,
                when='midnight',
                interval=1,
                backupCount=config.log_retention_days
            )
        ]
    )
    
    # Configure structured logging if available
    if HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        return structlog.get_logger("indian_market_engine")
    else:
        # Fallback to standard logger
        logger = logging.getLogger("indian_market_engine")
        logger.info("Using standard logging (structlog not available)")
        return logger


class LogEntry:
    """Standard log entry structure."""
    
    def __init__(
        self,
        category: str,
        event: str,
        data: Dict[str, Any],
        level: str = "INFO",
        engine: str = "indian_market_engine"
    ):
        self.timestamp = datetime.utcnow().isoformat()
        self.level = level
        self.engine = engine
        self.category = category
        self.event = event
        self.data = data
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert log entry to dictionary."""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "engine": self.engine,
            "category": self.category,
            "event": self.event,
            "data": self.data
        }
    
    def to_json(self) -> str:
        """Convert log entry to JSON string."""
        return json.dumps(self.to_dict())


def log_order_submitted(logger, ticket: str, symbol: str, side: str, 
                         quantity: int, price: float, order_type: str,
                         submission_time: datetime):
    """Log order submission."""
    logger.info(
        "order_submitted",
        category="order",
        event="submitted",
        ticket=ticket,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        order_type=order_type,
        submission_time=submission_time.isoformat()
    )


def log_position_opened(logger, ticket: str, symbol: str, side: str,
                        quantity: int, entry_price: float,
                        stop_loss: float, take_profit: float,
                        entry_time: datetime):
    """Log position opening."""
    logger.info(
        "position_opened",
        category="position",
        event="opened",
        ticket=ticket,
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        entry_time=entry_time.isoformat()
    )


def log_position_closed(logger, ticket: str, symbol: str,
                        realized_pnl: float, holding_seconds: int):
    """Log position closure."""
    logger.info(
        "position_closed",
        category="position",
        event="closed",
        ticket=ticket,
        symbol=symbol,
        realized_pnl=realized_pnl,
        holding_seconds=holding_seconds
    )


def log_ai_evaluation(logger, setup_id: str, symbol: str, 
                      decision: str, decision_score: float,
                      reasoning: str, evaluation_time_ms: float):
    """Log AI decision engine evaluation."""
    logger.info(
        "ai_evaluation",
        category="ai_decision",
        event="evaluated",
        setup_id=setup_id,
        symbol=symbol,
        decision=decision,
        decision_score=decision_score,
        reasoning=reasoning,
        evaluation_time_ms=evaluation_time_ms
    )


def log_error(logger, category: str, error_type: str, 
              message: str, details: Dict[str, Any] = None):
    """Log error with context."""
    logger.error(
        "error_occurred",
        category=category,
        event="error",
        error_type=error_type,
        message=message,
        details=details or {}
    )
