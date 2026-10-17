"""WiZ protocol adapters for controlling and discovering lights on the LAN."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

from pywizlight import PilotBuilder, wizlight
from pywizlight.discovery import discover_lights

from .models import LightState

GLOBAL_BROADCAST = "255.255.255.255"


@asynccontextmanager
async def wiz_bulb(ip_address: str) -> AsyncIterator[wizlight]:
    """Open a WiZ bulb connection and always release its UDP transport."""
    bulb = wizlight(ip_address)
    try:
        yield bulb
    finally:
        with suppress(Exception):
            await bulb.async_close()


@dataclass
class WizLightAdapter:
    """Translate Lumia light states to and from the WiZ pilot protocol."""

    timeout: float = 3.0

    @staticmethod
    def rgb(hex_color: str) -> tuple[int, int, int]:
        value = hex_color.lstrip("#")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    @staticmethod
    def hex_color(rgb: tuple[int, int, int] | None) -> str | None:
        return "#{:02X}{:02X}{:02X}".format(*rgb) if rgb and any(rgb) else None

    async def apply(
        self, ip_address: str, *, on=None, brightness=None, color=None, color_temp=None
    ) -> None:
        async with wiz_bulb(ip_address) as bulb:
            if on is False:
                await asyncio.wait_for(bulb.turn_off(), self.timeout)
                return
            if on is True or any(value is not None for value in (brightness, color, color_temp)):
                pilot = {}
                if brightness is not None:
                    pilot["brightness"] = round(brightness * 2.55)
                if color is not None:
                    pilot["rgb"] = self.rgb(color)
                if color_temp is not None:
                    pilot["colortemp"] = color_temp
                await asyncio.wait_for(bulb.turn_on(PilotBuilder(**pilot)), self.timeout)

    async def status(self, ip_address: str) -> dict:
        async with wiz_bulb(ip_address) as bulb:
            state = await asyncio.wait_for(bulb.updateState(), self.timeout)
            brightness = state.get_brightness()
            return {
                "on": bool(state.get_state()),
                "brightness": max(1, round(brightness / 2.55)) if brightness else None,
                "color": self.hex_color(state.get_rgb()),
                "color_temp": self.clamp_color_temp(state.get_colortemp()),
            }

    @staticmethod
    def clamp_color_temp(kelvin: int | None) -> int | None:
        """Fit a reported temperature into the range Lumia stores."""
        if not kelvin:
            return None
        return min(LightState.MAX_COLOR_TEMP, max(LightState.MIN_COLOR_TEMP, kelvin))


@dataclass
class WizDiscovery:
    """Discover WiZ bulbs by directed /24 probing or LAN broadcast."""

    wait_time: float = 5.0
    probe_timeout: float = 0.8
    concurrency: int = 64

    @staticmethod
    def identity(ip_address: str, mac_address: str | None) -> dict:
        return {"ip_address": ip_address, "mac_address": mac_address, "protocol": "wiz"}

    async def _probe(self, ip_address: str) -> dict | None:
        """Return device identity only when an address answers WiZ getPilot."""
        async with wiz_bulb(ip_address) as bulb:
            try:
                state = await asyncio.wait_for(bulb.updateState(), self.probe_timeout)
            except Exception:
                return None
            mac_address = (state.get_mac() or bulb.mac) if state is not None else None
        return self.identity(ip_address, mac_address) if state is not None else None

    async def _scan_network(self, network: IPv4Network) -> list[dict]:
        semaphore = asyncio.Semaphore(self.concurrency)

        async def limited_probe(address: IPv4Address) -> dict | None:
            async with semaphore:
                try:
                    return await self._probe(str(address))
                except Exception:
                    return None

        found = await asyncio.gather(*(limited_probe(host) for host in network.hosts()))
        return [result for result in found if result is not None]

    async def scan(self, broadcast_space: str = GLOBAL_BROADCAST) -> list[dict]:
        # Directed /24 scans work through Docker's bridge, unlike LAN broadcast
        # packets which commonly stop at the container boundary.
        if broadcast_space != GLOBAL_BROADCAST:
            broadcast = IPv4Address(broadcast_space)
            if not broadcast.is_private:
                raise ValueError("Discovery is limited to a private IPv4 network")
            return await self._scan_network(IPv4Network(f"{broadcast}/24", strict=False))
        bulbs = await discover_lights(broadcast_space=broadcast_space, wait_time=self.wait_time)
        return [self.identity(bulb.ip, bulb.mac) for bulb in bulbs]
