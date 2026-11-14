"""
╔══════════════════════════════════════════════════════════════╗
║        INDIAN MARKET ENGINE - CONFIGURATION MANAGEMENT       ║
║         Pydantic-based configuration with validation         ║
╚══════════════════════════════════════════════════════════════╝

Configuration management for the Indian Market Engine using Pydantic models
for runtime type checking and validation. Supports environment variables
and configuration files with comprehensive parameter validation.
"""

import os
from decimal import Decimal
from typing import Optional
try:
    from pydantic_settings import BaseSettings
    from pydantic import Field, SecretStr, field_validator as validator
except ImportError:
    from pydantic import BaseSettings, Field, SecretStr, validator


class EngineConfig(BaseSettings):
    """
    Indian Market Engine configuration with environment variable support.
    
    All configuration parameters can be set via environment variables
    with the prefix INDIAN_ENGINE_ (e.g., INDIAN_ENGINE_DHAN_CLIENT_ID).
    """
    
    # ═══ Dhan API Credentials ═══
    dhan_client_id: str = Field(..., description="Dhan client ID")
    dhan_access_token: SecretStr = Field(..., description="Dhan access token")
    dhan_api_url: str = Field(default="https://api.dhan.co", description="Dhan API base URL")
    dhan_websocket_url: str = Field(default="wss://api-feed.dhan.co", description="Dhan WebSocket URL")
    
    # ═══ Connection Settings ═══
    connection_timeout_sec: int = Field(default=30, ge=5, le=300, description="Connection timeout in seconds")
    max_connection_retries: int = Field(default=5, ge=1, le=20, description="Maximum connection retry attempts")
    heartbeat_interval_sec: int = Field(default=30, ge=10, le=300, description="Heartbeat check interval")
    
    # ═══ Circuit Breaker Settings ═══
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1, le=50, description="Failures before circuit opens")
    circuit_breaker_recovery_timeout_sec: int = Field(default=30, ge=10, le=600, description="Recovery timeout in seconds")
    circuit_breaker_half_open_attempts: int = Field(default=3, ge=1, le=10, description="Half-open test attempts")
    
    # ═══ Data Stream Settings ═══
    tick_buffer_size: int = Field(default=10000, ge=1000, le=100000, description="Tick data buffer size")
    max_tick_processing_latency_ms: float = Field(default=10.0, ge=1.0, le=100.0, description="Max tick processing latency")
    websocket_reconnect_delay_sec: int = Field(default=5, ge=1, le=60, description="WebSocket reconnection delay")
    
    # ═══ Instrument Cache Settings ═══
    instrument_cache_refresh_hour: int = Field(default=8, ge=0, le=23, description="Daily cache refresh hour (IST)")
    instrument_cache_ttl_hours: int = Field(default=24, ge=1, le=168, description="Cache TTL in hours")
    
    # ═══ Order Execution Settings ═══
    max_order_submission_latency_ms: float = Field(default=100.0, ge=10.0, le=5000.0, description="Max order submission latency")
    max_risk_validation_latency_ms: float = Field(default=150.0, ge=10.0, le=5000.0, description="Max risk validation latency")
    order_retry_attempts: int = Field(default=3, ge=1, le=10, description="Order retry attempts on failure")
    
    # ═══ Position Management Settings ═══
    max_position_update_latency_ms: float = Field(default=20.0, ge=1.0, le=200.0, description="Max position update latency")
    sl_tp_check_interval_sec: int = Field(default=1, ge=1, le=10, description="SL/TP trigger check interval")
    position_sync_interval_sec: int = Field(default=60, ge=10, le=600, description="Position synchronization interval")
    
    # ═══ Trading Mode Settings ═══
    intraday_mode: bool = Field(default=True, description="Enable intraday trading mode")
    auto_close_positions_at_session_end: bool = Field(default=True, description="Auto-close positions at market close")
    
    # ═══ Risk Limits ═══
    max_position_size: int = Field(default=1000, ge=1, le=100000, description="Maximum position size")
    max_portfolio_exposure: Decimal = Field(default=Decimal("100000.0"), ge=1000, description="Maximum portfolio exposure")
    max_daily_loss: Decimal = Field(default=Decimal("10000.0"), ge=100, description="Maximum daily loss limit")
    max_drawdown_percent: float = Field(default=10.0, ge=1.0, le=50.0, description="Maximum drawdown percentage")
    
    # ═══ Logging Settings ═══
    log_file: str = Field(default="logs/indian_engine.log", description="Log file path")
    log_level: str = Field(default="INFO", description="Logging level")
    log_retention_days: int = Field(default=90, ge=7, le=365, description="Log retention period in days")
    structured_logging: bool = Field(default=True, description="Enable structured JSONL logging")
    
    # ═══ Integration URLs ═══
    ai_engine_url: str = Field(default="http://localhost:8001", description="AI Decision Engine URL")
    risk_engine_url: str = Field(default="http://localhost:8002", description="Risk Engine URL")
    portfolio_url: str = Field(default="http://localhost:8003", description="Portfolio Manager URL")
    capital_url: str = Field(default="http://localhost:8004", description="Capital Allocator URL")
    analytics_url: str = Field(default="http://localhost:8005", description="Analytics Engine URL")
    learning_url: str = Field(default="http://localhost:8006", description="Learning Engine URL")
    memory_url: str = Field(default="http://localhost:8007", description="Memory Division URL")
    research_url: str = Field(default="http://localhost:8008", description="Research Division URL")
    voice_url: str = Field(default="http://localhost:8009", description="Voice Division URL")
    dashboard_url: str = Field(default="http://localhost:8010", description="Living Dashboard URL")
    
    # ═══ Performance Settings ═══
    max_concurrent_orders: int = Field(default=50, ge=1, le=1000, description="Maximum concurrent orders")
    max_concurrent_instruments: int = Field(default=100, ge=1, le=1000, description="Maximum concurrent instruments")
    
    # ═══ Simulation Mode ═══
    simulation_mode: bool = Field(default=False, description="Enable simulation mode")
    simulation_initial_balance: Decimal = Field(default=Decimal("100000.0"), ge=1000, description="Simulation starting balance")
    simulation_slippage_bps: float = Field(default=2.0, ge=0.0, le=50.0, description="Simulation slippage in basis points")
    
    # ═══ Feature Flags ═══
    enable_ai_integration: bool = Field(default=True, description="Enable AI decision integration")
    enable_risk_integration: bool = Field(default=True, description="Enable risk engine integration")
    enable_portfolio_integration: bool = Field(default=True, description="Enable portfolio manager integration")
    enable_learning_integration: bool = Field(default=True, description="Enable learning engine integration")
    enable_voice_integration: bool = Field(default=False, description="Enable voice command integration")
    
    class Config:
        env_file = ".env"
        env_prefix = "INDIAN_ENGINE_"
        case_sensitive = False
        
    @validator('dhan_client_id')
    def validate_client_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Dhan client ID cannot be empty')
        return v.strip()
    
    @validator('dhan_access_token')
    def validate_access_token(cls, v):
        if not v or len(v.get_secret_value().strip()) == 0:
            raise ValueError('Dhan access token cannot be empty')
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()
    
    @validator('max_portfolio_exposure', 'max_daily_loss', 'simulation_initial_balance')
    def validate_positive_decimal(cls, v):
        if v <= 0:
            raise ValueError('Value must be positive')
        return v
    
    def get_dhan_credentials(self) -> tuple[str, str]:
        """Get Dhan API credentials as tuple."""
        return self.dhan_client_id, self.dhan_access_token.get_secret_value()
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled."""
        feature_attr = f"enable_{feature_name}_integration"
        return getattr(self, feature_attr, False)
    
    def get_integration_config(self) -> dict:
        """Get all integration URLs as a dictionary."""
        return {
            "ai_engine": self.ai_engine_url,
            "risk_engine": self.risk_engine_url,
            "portfolio": self.portfolio_url,
            "capital": self.capital_url,
            "analytics": self.analytics_url,
            "learning": self.learning_url,
            "memory": self.memory_url,
            "research": self.research_url,
            "voice": self.voice_url,
            "dashboard": self.dashboard_url
        }
    
    def get_performance_limits(self) -> dict:
        """Get performance-related limits as a dictionary."""
        return {
            "max_tick_processing_latency_ms": self.max_tick_processing_latency_ms,
            "max_order_submission_latency_ms": self.max_order_submission_latency_ms,
            "max_risk_validation_latency_ms": self.max_risk_validation_latency_ms,
            "max_position_update_latency_ms": self.max_position_update_latency_ms,
            "max_concurrent_orders": self.max_concurrent_orders,
            "max_concurrent_instruments": self.max_concurrent_instruments
        }
    
    def get_risk_limits(self) -> dict:
        """Get risk management limits as a dictionary."""
        return {
            "max_position_size": self.max_position_size,
            "max_portfolio_exposure": float(self.max_portfolio_exposure),
            "max_daily_loss": float(self.max_daily_loss),
            "max_drawdown_percent": self.max_drawdown_percent
        }