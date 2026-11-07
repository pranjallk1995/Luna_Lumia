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

    @staticmethod
    def failed(reason: str) -> str:
        message = f"Luna Visia could not tag this image for Lumia: {reason}"
        logger.warning(message)
        return message
