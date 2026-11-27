"""Send each light's commands to the adapter for its protocol (WiZ, OpenRGB or iCUE)."""

from app.integrations import icue, openrgb
from app.integrations.icue import ICueAdapter, ICueAddress
from app.integrations.openrgb import OpenRGBAdapter, OpenRGBAddress


class LightRouter:
    def __init__(self, wiz, openrgb_adapter: OpenRGBAdapter, icue_adapter: ICueAdapter | None = None) -> None:
        self.wiz, self.openrgb, self.icue = wiz, openrgb_adapter, icue_adapter or ICueAdapter()

    def _for(self, address: str):
        if OpenRGBAddress.is_openrgb(address):
            return self.openrgb
        return self.icue if ICueAddress.is_icue(address) else self.wiz

    async def apply(self, address: str, keys: dict[str, str] | None = None, **state) -> None:
        adapter = self._for(address)
        if keys is not None and adapter in (self.icue, self.openrgb):
            await adapter.apply(address, keys=keys, **state)
        else:
            await adapter.apply(address, **state)

    async def keys(self, address: str) -> list[dict]:
        """Every key or LED of a PC light, by name, with its position."""
        if OpenRGBAddress.is_openrgb(address):
            return await self.openrgb.leds(address)
        if not ICueAddress.is_icue(address):
            raise ValueError("Only PC lights (iCUE and OpenRGB devices) take colors per key or LED")
        return await self.icue.keys(address)

    async def status(self, address: str) -> dict:
        return await self._for(address).status(address)


def light_address(light: dict) -> str:
    """The address a light's adapter understands: its IP, or a URL for PC devices."""
    if light.get("protocol") == "openrgb":
        port = light.get("port") or openrgb.DEFAULT_PORT
        return str(OpenRGBAddress(light["ip_address"], light["device"], port, light.get("zone"), light.get("leds")))
    if light.get("protocol") == "icue":
        port = light.get("port") or icue.DEFAULT_PORT
        return str(ICueAddress(light["ip_address"], light["device"], port))
    return light["ip_address"]
