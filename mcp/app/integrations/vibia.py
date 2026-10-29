"""What Luna Vibia is playing, read over luna_sentia_network."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

Row = dict[str, Any]


class VibiaUnavailableError(RuntimeError):
    """Raised when Luna Vibia is not configured or does not answer."""


class VibiaPlayback:
    """Luna Vibia's playback status, including the playing track's caption and tags."""

    TIMEOUT_SECONDS = 3.0
    # Vibia works a beat map out (about two seconds) the first time a track is asked for.
    BEATS_TIMEOUT_SECONDS = 30.0

    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)

    def status(self) -> Row:
        # output=0: Lumia needs the track, not which speaker it plays on (a slower lookup).
        return self._get("/api/playback?output=0", self.TIMEOUT_SECONDS)

    def beats(self, name: str) -> Row:
        """A track's beat times (seconds), their strengths (0-1), and its duration."""
        return self._get(f"/api/tracks/{urllib.parse.quote(name, safe='')}/beats", self.BEATS_TIMEOUT_SECONDS)

    def _get(self, path: str, timeout: float) -> Row:
        if not self.configured:
            raise VibiaUnavailableError(
                "Luna Vibia is not connected: set LUNAVIBIA_API_TOKEN in Lumia's .env "
                "(the same value as in Luna_Vibia/.env) and restart Lumia."
            )
        request = urllib.request.Request(f"{self.url}{path}", headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise VibiaUnavailableError(f"Luna Vibia did not answer at {self.url}: {error}") from error
