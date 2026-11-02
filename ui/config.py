"""Validated settings for the UI gateway and the browser app it serves."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse


@dataclass(frozen=True)
class SSOConfig:
    """Single sign-on through Luna Sentia; this block is identical in every Luna app's config.py."""

    COOKIE_NAME: ClassVar[str] = "luna_sso"
    SESSION_HEADER: ClassVar[str] = "X-Luna-Session"
    # How long a confirmed session is trusted before asking Sentia again, so a sign-out
    # in another app takes effect here within this many seconds.
    RECHECK_SECONDS: ClassVar[int] = 60
    LOOKUP_TIMEOUT_SECONDS: ClassVar[float] = 5.0
    SESSION_CACHE_ENTRIES: ClassVar[int] = 256

    public_url: str
    internal_url: str = "http://luna-sentia-auth:8000"

    @classmethod
    def from_env(cls) -> "SSOConfig":
        public_url = os.getenv("LUNA_SSO_URL", "").strip().rstrip("/")
        if not public_url:
            raise RuntimeError("LUNA_SSO_URL must be the public address of Luna Sentia's auth service.")
        internal_url = os.getenv("LUNA_SSO_INTERNAL_URL", "").strip().rstrip("/")
        return cls(public_url=public_url, internal_url=internal_url or cls.internal_url)


@dataclass(frozen=True)
class UIConfig:
    """Immutable gateway settings."""

    UI_ROOT: ClassVar[Path] = Path(__file__).resolve().parent
    # The built React app; the Dockerfile puts it here.
    STATIC_DIR: ClassVar[Path] = UI_ROOT / "static"
    API_TIMEOUT_SECONDS: ClassVar[float] = 8.0
    MAX_REQUEST_BYTES: ClassVar[int] = 1024 * 1024
    # Hashed bundles never change under the same name.
    IMMUTABLE_CACHE_CONTROL: ClassVar[str] = "private, max-age=31536000, immutable"
    CONTENT_SECURITY_POLICY: ClassVar[str] = (
        # Room and light pictures are stored in Luna Visia, at its public address.
        "default-src 'self'; img-src 'self' data: https: http:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )

    # Built-in color chips: hex -> label.
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
    WEEKDAY_NAMES: ClassVar[tuple[str, ...]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    # White-light range supported by WiZ bulbs, in Kelvin.
    MIN_COLOR_TEMP: ClassVar[int] = 2200
    MAX_COLOR_TEMP: ClassVar[int] = 6500
    DEFAULT_COLOR_TEMP: ClassVar[int] = 4000
    DISCOVERY_BROADCAST: ClassVar[str] = "192.168.1.255"
    # The backend's limit for light, room, and group names.
    NAME_MAX_CHARS: ClassVar[int] = 30
    MAX_SEQUENCE_STEPS: ClassVar[int] = 24

    api_url: str
    api_token: str
    allowed_emails: frozenset[str]
    sso: SSOConfig

    @classmethod
    def from_env(cls) -> "UIConfig":
        """Build and validate gateway configuration from environment variables."""
        api_url = os.getenv("LUNALUMIA_API_URL", "http://luna-lumia-mcp:8000").rstrip("/")
        parsed = urlparse(api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("LUNALUMIA_API_URL must be a valid HTTP(S) URL.")
        api_token = os.getenv("LUNALUMIA_API_TOKEN", "").strip()
        if len(api_token) < 32:
            raise RuntimeError("LUNALUMIA_API_TOKEN must contain at least 32 characters.")
        allowed_emails = frozenset(
            email.strip().casefold()
            for email in os.getenv("LUNALUMIA_ALLOWED_EMAILS", "").split(",")
            if email.strip()
        )
        if not allowed_emails:
            raise RuntimeError("LUNALUMIA_ALLOWED_EMAILS must list at least one account.")
        return cls(api_url=api_url, api_token=api_token, allowed_emails=allowed_emails, sso=SSOConfig.from_env())
