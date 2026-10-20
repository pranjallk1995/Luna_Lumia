"""Pure room-detection and room-image selection rules."""

from collections import Counter
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit


class RoomKeyDetector:
    """Map free-form light and room names onto known room-image keys."""

    FALLBACK = "living_room"
    KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
        (("bath", "washroom"), "bathroom"),
        (("bed",), "bedroom"),
        (("balcony", "terrace", "patio"), "balcony"),
        (("kitchen",), "kitchen"),
        (("dining",), "dining_room"),
        (("office", "study", "desk"), "home_office"),
        (("entrance", "entry", "hall", "foyer"), "entrance"),
        (("living", "lounge"), "living_room"),
    )

    @classmethod
    def detect(cls, name: str) -> str | None:
        normalized = name.lower()
        for keywords, room_key in cls.KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                return room_key
        return None

    @classmethod
    def for_name(cls, name: str) -> str:
        return cls.detect(name) or cls.FALLBACK

    @classmethod
    def for_member_names(cls, light_names: Iterable[str]) -> str | None:
        return next(
            (key for name in light_names if (key := cls.detect(name)) is not None),
            None,
        )


class ImageScheme:
    """Identify the image-source origin and path prefix shared by related URLs."""

    PUBLIC_MARKER = "/api/public/images/"

    @classmethod
    def key(cls, image_url: str | None) -> str | None:
        if not image_url:
            return None
        parsed = urlsplit(image_url)
        path = parsed.path
        scheme_path = (
            path.split(cls.PUBLIC_MARKER, 1)[0] + cls.PUBLIC_MARKER
            if cls.PUBLIC_MARKER in path
            else path.rsplit("/", 1)[0] + "/"
        )
        return f"{parsed.scheme}://{parsed.netloc}{scheme_path}"

    @classmethod
    def counts(cls, urls: Iterable[str | None]) -> Counter:
        return Counter(key for url in urls if (key := cls.key(url)) is not None)


class RoomImageCatalog:
    """Resolve room keys to configured image URLs with consistent fallbacks."""

    def __init__(self, images: list[dict[str, Any]]) -> None:
        self.images = images
        self.urls = {item["room_key"]: item["image_url"] for item in images}

    def __bool__(self) -> bool:
        return bool(self.images)

    @property
    def fallback_url(self) -> str | None:
        return self.urls.get(RoomKeyDetector.FALLBACK) or next(
            iter(self.urls.values()), None
        )

    def url_for(self, room_key: str) -> str | None:
        return self.urls.get(room_key) or self.fallback_url

    def scheme_counts(self, extra_urls: Iterable[str | None] = ()) -> Counter:
        return ImageScheme.counts(
            [*(item["image_url"] for item in self.images), *extra_urls]
        )

    def _matching(self, room_key: str, scheme: str | None = None):
        return next(
            (
                image
                for image in self.images
                if image["room_key"] == room_key
                and (scheme is None or ImageScheme.key(image["image_url"]) == scheme)
            ),
            None,
        )

    def select(self, room_key: str, preferred_scheme: str | None) -> dict[str, Any]:
        """Prefer the room in the preferred scheme, then relax scheme and room."""
        fallback = RoomKeyDetector.FALLBACK
        return (
            self._matching(room_key, preferred_scheme)
            or self._matching(fallback, preferred_scheme)
            or self._matching(room_key)
            or self._matching(fallback)
            or self.images[0]
        )
