"""
Configuration management for Indian Market Engine using Pydantic.
"""

from typing import Optional
try:
    from pydantic_settings import BaseSettings
    from pydantic import SecretStr, field_validator
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings, SecretStr, validator as field_validator


class EngineConfig(BaseSettings):
    """Indian Market Engine configuration with environment variable support."""
    
    # Dhan API Credentials
    dhan_client_id: str
    dhan_access_token: SecretStr
    dhan_api_url: str = "https://api.dhan.co"
    dhan_websocket_url: str = "wss://api-feed.dhan.co"
    
    # Connection Settings
    connection_timeout_sec: int = 30
    max_connection_retries: int = 5
    heartbeat_interval_sec: int = 30
    
    # Circuit Breaker Settings
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_sec: int = 30
    circuit_breaker_half_open_attempts: int = 3
    
    # Data Stream Settings
    tick_buffer_size: int = 10000
    max_tick_processing_latency_ms: float = 10.0
    
    # Instrument Cache Settings
    instrument_cache_refresh_hour: int = 8  # 08:00 IST
    
    # Order Execution Settings
    max_order_submission_latency_ms: float = 100.0
    max_risk_validation_latency_ms: float = 150.0
    
    # Position Management Settings
    max_position_update_latency_ms: float = 20.0
    sl_tp_check_interval_sec: int = 1
    
    # Intraday Settings
    intraday_mode: bool = True
    auto_close_positions_at_session_end: bool = True
    
    # Risk Limits
    max_position_size: int = 1000
    max_portfolio_exposure: float = 100000.0
    
    # Log Settings
    log_file: str = "logs/indian_engine.log"
    log_level: str = "INFO"
    log_retention_days: int = 90
    
    # Integration URLs
    ai_engine_url: str = "http://localhost:8001"
    risk_engine_url: str = "http://localhost:8002"
    portfolio_url: str = "http://localhost:8003"
    capital_url: str = "http://localhost:8004"
    analytics_url: str = "http://localhost:8005"
    learning_url: str = "http://localhost:8006"
    memory_url: str = "http://localhost:8007"
    research_url: str = "http://localhost:8008"
    voice_url: str = "http://localhost:8009"
    dashboard_url: str = "http://localhost:8010"
    
    # Simulation Mode
    simulation_mode: bool = False
    
    class Config:
        env_file = ".env"
        env_prefix = "INDIAN_ENGINE_"
        
    @field_validator("max_connection_retries")
    @classmethod
    def validate_retries(cls, v):
        if v < 1 or v > 10:
            raise ValueError("max_connection_retries must be between 1 and 10")
        return v
    
    @field_validator("heartbeat_interval_sec")
    @classmethod
    def validate_heartbeat(cls, v):
        if v < 10 or v > 120:
            raise ValueError("heartbeat_interval_sec must be between 10 and 120")
        return v
