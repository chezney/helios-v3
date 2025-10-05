"""
Helios Trading System V3.0 - Configuration Management
Complete settings with environment variable support
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from enum import Enum
from pathlib import Path
import os

# Find project root (where .env file is located)
def find_project_root():
    """Find the project root directory (where .env exists)"""
    current = Path(__file__).parent.parent  # config/ -> root
    if (current / '.env').exists():
        return str(current / '.env')
    # Fallback: search up to 3 levels
    for _ in range(3):
        current = current.parent
        if (current / '.env').exists():
            return str(current / '.env')
    return '.env'  # Default fallback

ENV_FILE_PATH = find_project_root()


class Environment(str, Enum):
    """Deployment environment"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class TradingMode(str, Enum):
    """Trading mode"""
    PAPER = "paper"
    LIVE = "live"


class DatabaseSettings(BaseSettings):
    """Database configuration"""

    model_config = {"extra": "allow", "env_file": ENV_FILE_PATH, "env_file_encoding": "utf-8"}

    # PostgreSQL
    postgres_host: str = Field(default="localhost", env="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    postgres_db: str = Field(default="helios_v3", env="POSTGRES_DB")
    postgres_user: str = Field(default="helios", env="POSTGRES_USER")
    postgres_password: str = Field(default="", env="POSTGRES_PASSWORD")

    # Redis
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")

    # InfluxDB
    influx_url: str = Field(default="http://localhost:8086", env="INFLUX_URL")
    influx_token: Optional[str] = Field(default=None, env="INFLUX_TOKEN")
    influx_org: str = Field(default="helios", env="INFLUX_ORG")
    influx_bucket: str = Field(default="market_data", env="INFLUX_BUCKET")

    @property
    def postgres_url(self) -> str:
        """PostgreSQL connection URL"""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def postgres_url_sync(self) -> str:
        """PostgreSQL sync connection URL (for Alembic)"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        """Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


class TradingSettings(BaseSettings):
    """Trading configuration"""

    model_config = {"extra": "allow"}

    mode: TradingMode = Field(default=TradingMode.PAPER, env="TRADING_MODE")

    # VALR API
    valr_api_key: str = Field(default="", env="VALR_API_KEY")
    valr_api_secret: str = Field(default="", env="VALR_API_SECRET")
    valr_base_url: str = Field(default="https://api.valr.com", env="VALR_BASE_URL")
    valr_websocket_url: str = Field(default="wss://api.valr.com/ws/trade", env="VALR_WEBSOCKET_URL")

    # Trading pairs
    trading_pairs: list[str] = Field(default=["BTCZAR", "ETHZAR", "SOLZAR"])

    # Risk limits
    max_position_size_pct: float = Field(default=0.20, env="MAX_POSITION_SIZE_PCT")
    max_leverage: float = Field(default=3.0, env="MAX_LEVERAGE")
    max_drawdown_pct: float = Field(default=0.15, env="MAX_DRAWDOWN_PCT")
    daily_loss_limit_pct: float = Field(default=0.05, env="DAILY_LOSS_LIMIT_PCT")


class MLSettings(BaseSettings):
    """Machine Learning configuration"""

    model_config = {"extra": "allow"}

    # Model paths
    model_path: str = Field(default="models/helios_neural_network_40m_best.pt", env="MODEL_PATH")
    scaler_path: str = Field(default="models/feature_scaler_40m.pkl", env="SCALER_PATH")

    # Training config (RTX 4060 optimized)
    batch_size: int = Field(default=16, env="ML_BATCH_SIZE")
    accumulation_steps: int = Field(default=2, env="ML_ACCUMULATION_STEPS")
    mixed_precision: bool = Field(default=True, env="ML_MIXED_PRECISION")
    gradient_checkpointing: bool = Field(default=True, env="ML_GRADIENT_CHECKPOINTING")

    # Device
    device: str = Field(default="cuda", env="ML_DEVICE")

    # Feature engineering
    num_features: int = 90
    features_per_timeframe: int = 30


class LLMSettings(BaseSettings):
    """LLM configuration"""

    model_config = {"extra": "allow"}

    # Provider
    provider: str = Field(default="anthropic", env="LLM_PROVIDER")

    # API Keys
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")

    # Models
    anthropic_model: str = Field(default="claude-3-5-sonnet-20241022", env="ANTHROPIC_MODEL")
    openai_model: str = Field(default="gpt-4-turbo-preview", env="OPENAI_MODEL")

    # Generation settings
    temperature: float = Field(default=0.3, env="LLM_TEMPERATURE")
    max_tokens: int = Field(default=1024, env="LLM_MAX_TOKENS")


class RiskSettings(BaseSettings):
    """Risk management configuration"""

    model_config = {"extra": "allow"}

    # GARCH settings
    garch_lookback_days: int = Field(default=30, env="GARCH_LOOKBACK_DAYS")
    garch_update_interval_hours: int = Field(default=4, env="GARCH_UPDATE_INTERVAL_HOURS")

    # Kelly Criterion
    fractional_kelly: float = Field(default=0.25, env="FRACTIONAL_KELLY")
    min_confidence: float = Field(default=0.55, env="MIN_CONFIDENCE")
    reward_risk_ratio: float = Field(default=2.0, env="REWARD_RISK_RATIO")


class LoggingSettings(BaseSettings):
    """Logging configuration"""

    model_config = {"extra": "allow"}

    level: str = Field(default="INFO", env="LOG_LEVEL")
    format: str = Field(default="json", env="LOG_FORMAT")
    log_dir: str = Field(default="logs", env="LOG_DIR")
    rotation: str = Field(default="1 day", env="LOG_ROTATION")
    retention: str = Field(default="30 days", env="LOG_RETENTION")


class Settings(BaseSettings):
    """Main application settings"""

    model_config = {"extra": "allow", "env_file": ENV_FILE_PATH, "env_file_encoding": "utf-8", "case_sensitive": False}

    # Environment
    environment: Environment = Field(default=Environment.DEVELOPMENT, env="ENVIRONMENT")

    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    ml: MLSettings = Field(default_factory=MLSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # Feature flags
    enable_auto_trading: bool = Field(default=False, env="ENABLE_AUTO_TRADING")
    enable_websocket: bool = Field(default=True, env="ENABLE_WEBSOCKET")
    enable_ml_predictions: bool = Field(default=True, env="ENABLE_ML_PREDICTIONS")
    enable_llm_analysis: bool = Field(default=True, env="ENABLE_LLM_ANALYSIS")

    # Security
    secret_key: str = Field(default="change-me-in-production", env="SECRET_KEY")

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


# Global settings instance
settings = Settings()
