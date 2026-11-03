"""iCUE client: drive Corsair devices through the bridge on the PC that runs iCUE.

iCUE's SDK only works on its own machine, so ``bridge/icue_bridge.py`` runs there
and takes whole-device colors over HTTP. Each iCUE device becomes one Lumia light,
so schemes, schedules, weather and music treat it like any bulb.
"""

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from app.integrations.solid_color import SolidColors

DEFAULT_PORT = 6743
SCHEME = "icue://"


@dataclass(frozen=True)
class ICueAddress:
    """Where one iCUE device lives: the PC's IP, the bridge port, and the device name."""

    host: str
    device: str
    port: int = DEFAULT_PORT

    def __str__(self) -> str:
        return f"{SCHEME}{self.host}:{self.port}/{self.device}"

    @classmethod
    def parse(cls, address: str) -> "ICueAddress":
        if not address.startswith(SCHEME):
            raise ValueError(f"Not an iCUE address: {address}")
        location, _, device = address[len(SCHEME):].partition("/")
        host, _, port = location.partition(":")
        if not host or not device:
            raise ValueError(f"Incomplete iCUE address: {address}")
        return cls(host, device, int(port or DEFAULT_PORT))

    @staticmethod
    def is_icue(address: str) -> bool:
        return address.startswith(SCHEME)


@dataclass
class ICueAdapter:
    """Translate Lumia light states into whole-device colors on the iCUE bridge."""

    token: str = ""  # used for any PC without its own entry in host_tokens
    timeout: float = 3.0
    host_tokens: dict[str, str] = field(default_factory=dict)
    colors: SolidColors = field(default_factory=SolidColors)

    def _request(self, host: str, port: int, method: str, path: str, body: dict | None = None):
        token = self.host_tokens.get(host, self.token)
        if not token:
            raise ConnectionError(f"No iCUE bridge token for {host}: set LUNALUMIA_ICUE_TOKENS")
        request = urllib.request.Request(
            f"http://{host}:{port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                message = json.load(error).get("error", error.reason)
            if error.code == 404:
                raise LookupError(message) from error
            raise ConnectionError(f"iCUE bridge on {host}: {message}") from error
        except OSError as error:  # URLError included: the bridge or PC is down
            raise ConnectionError(f"iCUE bridge on {host} is unreachable: {error}") from error

    async def apply(
        self, address: str, *, on=None, brightness=None, color=None, color_temp=None
    ) -> None:
        if on is None and all(value is None for value in (brightness, color, color_temp)):
            return
        target = ICueAddress.parse(address)
        rgb = self.colors.target(
            str(target), on=on, brightness=brightness, color=color, color_temp=color_temp
        )
        path = f"/devices/{urllib.parse.quote(target.device, safe='')}/color"
        await asyncio.to_thread(
            self._request, target.host, target.port, "PUT", path, {"rgb": list(rgb)}
        )

    async def status(self, address: str) -> dict:
        """Confirm iCUE serves the device; its color stays as Lumia last set it."""
        target = ICueAddress.parse(address)
        devices = await self.devices(target.host, target.port)
        if target.device not in {device["device"] for device in devices}:
            raise LookupError(f"iCUE has no device named {target.device!r} on {target.host}")
        return {"mac_address": None}

    async def devices(self, host: str, port: int = DEFAULT_PORT) -> list[dict]:
        """The devices iCUE offers, as {"device": name, "led_count": n}."""
        return await asyncio.to_thread(self._request, host, port, "GET", "/devices")
