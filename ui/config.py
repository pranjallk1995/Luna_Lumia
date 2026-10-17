"""Validated presentation and service settings for the Streamlit UI."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse


@dataclass(frozen=True)
class UIConfig:
    """Immutable UI layout and backend-connection settings."""

    UI_ROOT: ClassVar[Path] = Path(__file__).resolve().parent
    LOGO_PATH: ClassVar[Path] = UI_ROOT / "assets" / "lunalumia_logo.png"
    PRESET_COLORS: ClassVar[tuple[str, ...]] = (
        "#F5F5F5",
        "#FFBE55",
        "#FF836A",
        "#B86DE0",
    )
    WEEKDAY_NAMES: ClassVar[tuple[str, ...]] = (
        "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
    )
    # White-light range supported by WiZ bulbs, in Kelvin.
    MIN_COLOR_TEMP: ClassVar[int] = 2200
    MAX_COLOR_TEMP: ClassVar[int] = 6500
    DEFAULT_COLOR_TEMP: ClassVar[int] = 4000
    # Matches the backend's light-status poll interval.
    STATUS_REFRESH_SECONDS: ClassVar[int] = 10

    api_url: str
    api_timeout: float = 8.0
    discovery_broadcast: str = "192.168.1.255"
    card_columns: int = 3

    @classmethod
    def from_env(cls) -> "UIConfig":
        api_url = os.getenv("LUNALUMIA_API_URL", "http://127.0.0.1:18002").rstrip("/")
        parsed = urlparse(api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("LUNALUMIA_API_URL must be a valid HTTP(S) URL.")
        return cls(api_url=api_url)
