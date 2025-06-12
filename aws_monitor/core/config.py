"""Configuration management for AWS Cost & Usage Monitor."""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


@dataclass
class AWSConfig:
    """AWS-specific configuration."""

    region: str = "us-east-1"
    profile: Optional[str] = None
    role_arn: Optional[str] = None
    cross_account_role_name: str = "AWSCostMonitorCrossAccountRole"
    external_id: Optional[str] = None
    max_parallel_threads: int = 10
    # Note: Hourly granularity removed - requires $80/month paid feature


@dataclass
class ApplicationConfig:
    """Application-specific configuration."""

    cost_anomaly_threshold: float = 20.0
    data_refresh_interval: int = 300
    cache_ttl_seconds: int = 300
    log_level: str = "INFO"
    enable_forecasting: bool = True
    enable_anomaly_detection: bool = True
    enable_resource_inventory: bool = True


@dataclass
class StreamlitConfig:
    """Streamlit-specific configuration."""

    server_port: int = 8501
    server_address: str = "0.0.0.0"
    server_headless: bool = True
    browser_gather_usage_stats: bool = False


@dataclass
class Config:
    """Main configuration class."""

    aws: AWSConfig = field(default_factory=AWSConfig)
    app: ApplicationConfig = field(default_factory=ApplicationConfig)
    streamlit: StreamlitConfig = field(default_factory=StreamlitConfig)

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Config":
        """
        Load configuration from environment variables.

        Args:
            env_file: Path to .env file (optional)

        Returns:
            Config instance
        """
        if env_file:
            load_dotenv(env_file)
        else:
            # Try to load from default locations
            env_path = Path(".env")
            if env_path.exists():
                load_dotenv(env_path)
            else:
                # Try parent directory
                parent_env = Path("../.env")
                if parent_env.exists():
                    load_dotenv(parent_env)

        # Load AWS config
        aws_config = AWSConfig(
            region=os.getenv("AWS_REGION", "us-east-1"),
            profile=os.getenv("AWS_PROFILE"),
            role_arn=os.getenv("AWS_ROLE_ARN"),
            cross_account_role_name=os.getenv(
                "CROSS_ACCOUNT_ROLE_NAME", "AWSCostMonitorCrossAccountRole"
            ),
            external_id=os.getenv("EXTERNAL_ID"),
            max_parallel_threads=int(os.getenv("MAX_PARALLEL_THREADS", "10")),
        )

        # Load application config
        app_config = ApplicationConfig(
            cost_anomaly_threshold=float(os.getenv("COST_ANOMALY_THRESHOLD", "20.0")),
            data_refresh_interval=int(os.getenv("DATA_REFRESH_INTERVAL", "300")),
            cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "300")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            enable_forecasting=os.getenv("ENABLE_FORECASTING", "true").lower() == "true",
            enable_anomaly_detection=os.getenv("ENABLE_ANOMALY_DETECTION", "true").lower()
            == "true",
            enable_resource_inventory=os.getenv("ENABLE_RESOURCE_INVENTORY", "true").lower()
            == "true",
        )

        # Load Streamlit config
        streamlit_config = StreamlitConfig(
            server_port=int(os.getenv("STREAMLIT_SERVER_PORT", "8501")),
            server_address=os.getenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0"),
            server_headless=os.getenv("STREAMLIT_SERVER_HEADLESS", "true").lower() == "true",
            browser_gather_usage_stats=os.getenv(
                "STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false"
            ).lower()
            == "true",
        )

        config = cls(aws=aws_config, app=app_config, streamlit=streamlit_config)

        logger.info("Configuration loaded successfully")
        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "aws": {
                "region": self.aws.region,
                "profile": self.aws.profile,
                "role_arn": self.aws.role_arn,
                "cross_account_role_name": self.aws.cross_account_role_name,
                "external_id": self.aws.external_id,
                "max_parallel_threads": self.aws.max_parallel_threads,
            },
            "app": {
                "cost_anomaly_threshold": self.app.cost_anomaly_threshold,
                "data_refresh_interval": self.app.data_refresh_interval,
                "cache_ttl_seconds": self.app.cache_ttl_seconds,
                "log_level": self.app.log_level,
                "enable_forecasting": self.app.enable_forecasting,
                "enable_anomaly_detection": self.app.enable_anomaly_detection,
                "enable_resource_inventory": self.app.enable_resource_inventory,
            },
            "streamlit": {
                "server_port": self.streamlit.server_port,
                "server_address": self.streamlit.server_address,
                "server_headless": self.streamlit.server_headless,
                "browser_gather_usage_stats": self.streamlit.browser_gather_usage_stats,
            },
        }

    def validate(self) -> bool:
        """
        Validate configuration.

        Returns:
            True if valid, raises ValueError if not
        """
        # Validate AWS config
        if not self.aws.region:
            raise ValueError("AWS region is required")

        if self.aws.role_arn and not self.aws.role_arn.startswith("arn:aws:iam::"):
            raise ValueError("Invalid AWS role ARN format")

        # Validate application config
        if self.app.cost_anomaly_threshold < 0 or self.app.cost_anomaly_threshold > 100:
            raise ValueError("Cost anomaly threshold must be between 0 and 100")

        if self.app.data_refresh_interval < 60:
            raise ValueError("Data refresh interval must be at least 60 seconds")

        if self.app.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(f"Invalid log level: {self.app.log_level}")

        # Validate Streamlit config
        if self.streamlit.server_port < 1 or self.streamlit.server_port > 65535:
            raise ValueError("Invalid Streamlit server port")

        return True


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Returns:
        Config instance
    """
    global _config
    if _config is None:
        _config = Config.from_env()
        try:
            _config.validate()
        except ValueError as e:
            logger.error(f"Configuration validation failed: {e}")
            # Use defaults if validation fails
            _config = Config()
    return _config


def set_config(config: Config) -> None:
    """
    Set the global configuration instance.

    Args:
        config: Config instance to set
    """
    global _config
    config.validate()
    _config = config


def reset_config() -> None:
    """Reset configuration to None (useful for testing)."""
    global _config
    _config = None
