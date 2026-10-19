"""Validated runtime configuration for the Luna Lumia backend."""

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class AppConfig:
    """Immutable backend settings loaded from environment variables."""

    database_url: str
    api_token: str
    timezone: ZoneInfo = ZoneInfo("Asia/Kolkata")
    host: str = "0.0.0.0"
    port: int = 8000
    schedule_interval_seconds: float = 20.0
    device_timeout_seconds: float = 3.0
    default_broadcast_space: str = "255.255.255.255"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build and validate backend configuration from the environment."""
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required.")
        api_token = os.getenv("LUNALUMIA_API_TOKEN", "").strip()
        if len(api_token) < 32:
            raise RuntimeError("LUNALUMIA_API_TOKEN must contain at least 32 characters.")
        return cls(
            database_url=database_url,
            api_token=api_token,
            timezone=ZoneInfo(os.getenv("TZ", "Asia/Kolkata")),
        )
