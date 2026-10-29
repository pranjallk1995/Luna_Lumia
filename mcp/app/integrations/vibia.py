"""What Luna Vibia is playing, read over luna_sentia_network."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

Row = dict[str, Any]


class VibiaUnavailableError(RuntimeError):
    """Raised when Luna Vibia is not configured or does not answer."""


class VibiaPlayback:
    """Luna Vibia's playback status, including the playing track's caption and tags."""

    TIMEOUT_SECONDS = 3.0

    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)

    def status(self) -> Row:
        if not self.configured:
            raise VibiaUnavailableError(
                "Luna Vibia is not connected: set LUNAVIBIA_API_TOKEN in Lumia's .env "
                "(the same value as in Luna_Vibia/.env) and restart Lumia."
            )
        # output=0: Lumia needs the track, not which speaker it plays on (a slower lookup).
        request = urllib.request.Request(
            f"{self.url}/api/playback?output=0", headers={"Authorization": f"Bearer {self.token}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise VibiaUnavailableError(f"Luna Vibia did not answer at {self.url}: {error}") from error
