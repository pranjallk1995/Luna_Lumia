"""Tag the Luna Visia images Lumia shows, so Visia records that Lumia uses them."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from app.core import tenancy

logger = logging.getLogger(__name__)


class VisiaImageTagger:
    """Add the "luna lumia" tag to the Visia images rooms and lights show.

    Lumia also accepts pictures from anywhere, and works without Visia, so tagging
    is best-effort: a URL that is not a Visia image-ID URL is left alone, and a
    failure is logged and reported back instead of refusing the picture.
    """

    TAGS = ("luna lumia",)
    PUBLIC_PATH = re.compile(
        r"/api/public/images/"
        r"(?P<image_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$",
        re.IGNORECASE,
    )

    def __init__(self, api_url: str, companion_token: str = "", timeout: float = 10.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.api_url = api_url.rstrip("/")
        self.companion_token = companion_token
        self.timeout = timeout
        self.transport = transport

    @classmethod
    def image_id(cls, image_url: str | None) -> str | None:
        parsed = urlparse((image_url or "").strip())
        match = cls.PUBLIC_PATH.search(parsed.path)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not match:
            return None
        return match["image_id"].lower()

    def tag(self, image_url: str | None) -> str | None:
        """Tag the Visia image ``image_url`` names: "tagged", an error message, or None if not Visia's."""
        image_id = self.image_id(image_url)
        if image_id is None:
            return None
        if not self.companion_token:
            return self.failed("set LUNAVISIA_COMPANION_TOKEN to the same value in Luna Lumia and Luna Visia")
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(
                    f"{self.api_url}/api/companion/images/tags",
                    json={"image_ids": [image_id], "tags": list(self.TAGS)},
                    headers={"Authorization": f"Bearer {self.companion_token}", tenancy.USER_HEADER: tenancy.current()},
                )
            response.raise_for_status()
            failed = response.json().get("failed") or []
        except (httpx.HTTPError, ValueError) as error:
            return self.failed(str(error))
        if failed:
            return self.failed(str(failed[0].get("error")))
        return "tagged"

    # Visia captions each new image with its vision model before answering.
    STORE_TIMEOUT_SECONDS = 300.0
    STORE_ATTEMPTS = 2

    def store(self, name: str, tags: list[str], content_base64: str) -> dict:
        """Store a new picture in Visia, tagged; return Visia's answer with its public_url.

        Unlike tagging this is not best-effort: a picture the person chose must be kept,
        so a failure raises. Visia answers identical bytes with the image it already has.
        """
        if not self.companion_token:
            raise ValueError(
                "Storing pictures in Luna Visia is off: set LUNAVISIA_COMPANION_TOKEN to the "
                "same value in Luna Lumia and Luna Visia."
            )
        failure = ""
        for _ in range(self.STORE_ATTEMPTS):
            try:
                with httpx.Client(timeout=self.STORE_TIMEOUT_SECONDS, transport=self.transport) as client:
                    response = client.post(
                        f"{self.api_url}/api/companion/images",
                        json={"name": name, "tags": [*self.TAGS, *tags], "content_base64": content_base64},
                        headers={"Authorization": f"Bearer {self.companion_token}", tenancy.USER_HEADER: tenancy.current()},
                    )
            except httpx.TransportError as error:
                failure = f"{type(error).__name__}: {error}"
                continue
            if response.status_code < 500:
                break
            failure = f"HTTP {response.status_code}"
        else:
            raise ConnectionError(f"Luna Visia could not store the picture ({failure}); try again.")
        if response.status_code == 401:
            raise ValueError("Luna Visia rejected Lumia's LUNAVISIA_COMPANION_TOKEN; set the same value in both apps.")
        if response.status_code >= 400:
            try:
                detail = response.json().get("error") or response.text
            except ValueError:
                detail = response.text
            raise ValueError(f"Luna Visia did not store the picture: {detail}")
        return response.json()

    @staticmethod
    def failed(reason: str) -> str:
        message = f"Luna Visia could not tag this image for Lumia: {reason}"
        logger.warning(message)
        return message
