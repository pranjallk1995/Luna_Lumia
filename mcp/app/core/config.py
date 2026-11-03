"""Validated runtime configuration for the Luna Lumia backend."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class AppConfig:
    """Immutable backend settings loaded from environment variables."""

    ASSET_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent / "assets"
    # Discovery scans this address unless a subnet broadcast is given.
    GLOBAL_BROADCAST: ClassVar[str] = "255.255.255.255"
    DB_POOL_MAX_SIZE: ClassVar[int] = 8
    # Scene playback: ~8 frame updates per second per light, and an unreachable bulb
    # must not stall the other lights' frames.
    PLAYBACK_FRAME_SECONDS: ClassVar[float] = 0.12
    PLAYBACK_SEND_TIMEOUT_SECONDS: ClassVar[float] = 0.35
    PLAYBACK_CALL_TIMEOUT_SECONDS: ClassVar[float] = 5.0

    database_url: str
    api_token: str
    timezone: ZoneInfo = ZoneInfo("Asia/Kolkata")
    host: str = "0.0.0.0"
    port: int = 8000
    schedule_interval_seconds: float = 20.0
    device_timeout_seconds: float = 3.0
    # Public origin of this MCP server, used for icon URLs ("" = embedded icons only).
    mcp_public_url: str = "http://localhost:18002"
    # Luna Vibia, whose playing track picks the music scheme ("" token = music off).
    vibia_api_url: str = "http://luna-vibia-mcp:8000"
    vibia_api_token: str = ""
    # Shared with the iCUE bridges on PCs, for Corsair devices: one token for any PC,
    # and per-PC tokens, which win ("" and empty = no iCUE lights).
    icue_token: str = ""
    icue_host_tokens: dict[str, str] = field(default_factory=dict)
    # Checks for a new track this often, so the lights (and beat pulses) change soon after it starts.
    music_interval_seconds: float = 2.0
    LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

    @staticmethod
    def parse_host_tokens(value: str) -> dict[str, str]:
        """Read "192.168.1.15=token,192.168.1.20=token" into a host -> token map."""
        tokens = {}
        for entry in filter(None, (item.strip() for item in value.split(","))):
            host, separator, token = entry.partition("=")
            if not separator or not host or not token:
                raise RuntimeError("LUNALUMIA_ICUE_TOKENS must look like 192.168.1.15=token,192.168.1.20=token")
            tokens[host.strip()] = token.strip()
        return tokens

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build and validate backend configuration from the environment."""
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required.")
        api_token = os.getenv("LUNALUMIA_API_TOKEN", "").strip()
        if len(api_token) < 32:
            raise RuntimeError("LUNALUMIA_API_TOKEN must contain at least 32 characters.")
        mcp_public_url = os.getenv("MCP_PUBLIC_URL", cls.mcp_public_url).strip().rstrip("/")
        if mcp_public_url:
            parsed_public_url = urlparse(mcp_public_url)
            local = parsed_public_url.scheme == "http" and parsed_public_url.hostname in cls.LOCAL_HOSTS
            if not (parsed_public_url.scheme == "https" or local) or not parsed_public_url.netloc:
                raise RuntimeError("MCP_PUBLIC_URL must be an HTTPS URL, or HTTP on localhost.")
        return cls(
            vibia_api_url=os.getenv("LUNAVIBIA_API_URL", cls.vibia_api_url).strip().rstrip("/"),
            vibia_api_token=os.getenv("LUNAVIBIA_API_TOKEN", "").strip(),
            icue_token=os.getenv("LUNALUMIA_ICUE_TOKEN", "").strip(),
            icue_host_tokens=cls.parse_host_tokens(os.getenv("LUNALUMIA_ICUE_TOKENS", "")),
            mcp_public_url=mcp_public_url,
            database_url=database_url,
            api_token=api_token,
            timezone=ZoneInfo(os.getenv("TZ", "Asia/Kolkata")),
        )
