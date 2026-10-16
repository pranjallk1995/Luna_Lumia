import asyncio
from contextlib import suppress
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

from pywizlight import PilotBuilder, wizlight
from pywizlight.discovery import discover_lights


@dataclass
class WizLightAdapter:
    timeout: float = 3.0

    @staticmethod
    def rgb(hex_color: str) -> tuple[int, int, int]:
        value = hex_color.lstrip("#")
        return tuple(int(value[index:index+2], 16) for index in (0, 2, 4))

    async def apply(self, ip_address: str, *, on=None, brightness=None, color=None):
        bulb = wizlight(ip_address)
        try:
            if on is False:
                await asyncio.wait_for(bulb.turn_off(), self.timeout)
                return
            if on is True or brightness is not None or color is not None:
                kwargs = {}
                if brightness is not None: kwargs["brightness"] = round(brightness * 2.55)
                if color is not None: kwargs["rgb"] = self.rgb(color)
                await asyncio.wait_for(bulb.turn_on(PilotBuilder(**kwargs)), self.timeout)
        finally:
            with suppress(Exception):
                await bulb.async_close()

    async def status(self, ip_address: str) -> dict:
        bulb = wizlight(ip_address)
        try:
            state = await asyncio.wait_for(bulb.updateState(), self.timeout)
            brightness = state.get_brightness()
            rgb = state.get_rgb()
            return {
                "on": bool(state.get_state()),
                "brightness": max(1, round(brightness / 2.55)) if brightness else None,
                "color": (
                    "#{:02X}{:02X}{:02X}".format(*rgb)
                    if rgb and any(rgb)
                    else None
                ),
            }
        finally:
            with suppress(Exception):
                await bulb.async_close()


@dataclass
class WizDiscovery:
    """Discover WiZ bulbs through their LAN broadcast protocol."""

    wait_time: float = 5.0
    probe_timeout: float = 0.8
    concurrency: int = 64

    async def _probe(self, ip_address: str) -> dict | None:
        """Return device identity only when an address answers WiZ getPilot."""
        bulb = wizlight(ip_address)
        try:
            state = await asyncio.wait_for(
                bulb.updateState(),
                timeout=self.probe_timeout,
            )
        except Exception:
            return None
        finally:
            with suppress(Exception):
                await bulb.async_close()
        if state is not None:
            return {
                "ip_address": ip_address,
                "mac_address": state.get_mac() or bulb.mac,
                "protocol": "wiz",
            }
        return None

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

    async def scan(self, broadcast_space: str = "255.255.255.255") -> list[dict]:
        # Directed /24 scans work through Docker's bridge, unlike LAN broadcast
        # packets which commonly stop at the container boundary.
        if broadcast_space != "255.255.255.255":
            broadcast = IPv4Address(broadcast_space)
            if not broadcast.is_private:
                raise ValueError("Discovery is limited to a private IPv4 network")
            network = IPv4Network(f"{broadcast}/24", strict=False)
            return await self._scan_network(network)
        bulbs = await discover_lights(
            broadcast_space=broadcast_space,
            wait_time=self.wait_time,
        )
        return [
            {
                "ip_address": bulb.ip,
                "mac_address": bulb.mac,
                "protocol": "wiz",
            }
            for bulb in bulbs
        ]


class LightController:
    def __init__(self, repository, adapter=None):
        self.repository = repository
        self.adapter = adapter or WizLightAdapter()

    async def control(self, target_type, target_id, state):
        lights = self.repository.target_lights(target_type, target_id)
        results = []
        for light in lights:
            try:
                await self.adapter.apply(light["ip_address"], on=state.on, brightness=state.brightness, color=state.color)
                saved = self.repository.update_state(light["id"], on=state.on, brightness=state.brightness, color=state.color.upper() if state.color else None, reachable=True)
                results.append({"light": saved, "ok": True})
            except Exception as error:
                self.repository.update_state(light["id"], reachable=False)
                results.append({"light": light, "ok": False, "error": str(error)})
        return results

    async def poll_statuses(self):
        async def poll(light):
            try:
                state = await self.adapter.status(light["ip_address"])
                saved = self.repository.update_state(
                    light["id"], **state, reachable=True
                )
                return {"light": saved, "ok": True}
            except Exception as error:
                saved = self.repository.update_state(light["id"], reachable=False)
                return {"light": saved or light, "ok": False, "error": str(error)}

        return await asyncio.gather(
            *(poll(light) for light in self.repository.target_lights("all", None))
        )
