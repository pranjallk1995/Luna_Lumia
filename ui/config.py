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
    # Built-in color chips: hex -> label. Iterating yields the hex values.
    # Balanced for the dark UI and checked as a set (dataviz palette validator,
    # dark surface): distinct for normal and color-blind vision, >= 3:1 contrast.
    PRESET_COLORS: ClassVar[dict[str, str]] = {
        "#2BC8E2": "Cyan",
        "#F4BC42": "Amber",
        "#EE6860": "Coral",
        "#CF5BD8": "Magenta",
    }
    # Built-in solid schemes offered as one-tap chips in a light card's Temperature mode.
    TEMPERATURE_PRESETS: ClassVar[tuple[str, ...]] = ("Focus", "Daylight", "Reading", "Bedtime")
    WEEKDAY_NAMES: ClassVar[tuple[str, ...]] = (
        "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
    )
    # White-light range supported by WiZ bulbs, in Kelvin.
    MIN_COLOR_TEMP: ClassVar[int] = 2200
    MAX_COLOR_TEMP: ClassVar[int] = 6500
    DEFAULT_COLOR_TEMP: ClassVar[int] = 4000

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
