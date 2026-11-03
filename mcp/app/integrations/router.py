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

    async def apply(self, address: str, **state) -> None:
        await self._for(address).apply(address, **state)

    async def status(self, address: str) -> dict:
        return await self._for(address).status(address)


def light_address(light: dict) -> str:
    """The address a light's adapter understands: its IP, or a URL for PC devices."""
    if light.get("protocol") == "openrgb":
        port = light.get("port") or openrgb.DEFAULT_PORT
        return str(OpenRGBAddress(light["ip_address"], light["device"], port))
    if light.get("protocol") == "icue":
        port = light.get("port") or icue.DEFAULT_PORT
        return str(ICueAddress(light["ip_address"], light["device"], port))
    return light["ip_address"]
