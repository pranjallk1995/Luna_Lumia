from .models import LightCreate, LightState


class LumiaService:
    def __init__(self, repository, controller, discovery):
        self.repository, self.controller, self.discovery = repository, controller, discovery
    def ensure_schema(self): self.repository.ensure_schema()

    async def control(self, target_type, target_id, state):
        if target_type != "all" and target_id is None: raise ValueError("target_id is required")
        return await self.controller.control(target_type, target_id, state)

    async def apply_scene(self, target_type, target_id, scene_id):
        scene = self.repository.scene(scene_id)
        if not scene: raise ValueError("Scene not found")
        return await self.control(target_type,target_id,LightState(on=True,brightness=scene["brightness"],color=scene["color"]))

    async def discover(self, broadcast_space="255.255.255.255"):
        configured = {light["ip_address"]: light for light in self.repository.list_lights()}
        results = await self.discovery.scan(broadcast_space)
        for result in results:
            saved_light = configured.get(result["ip_address"])
            result["configured"] = saved_light is not None
            if saved_light and result.get("mac_address") and saved_light.get("mac_address") != result["mac_address"]:
                normalized = LightCreate(
                    name=saved_light["name"],
                    ip_address=saved_light["ip_address"],
                    protocol=saved_light["protocol"],
                    mac_address=result["mac_address"],
                ).mac_address
                self.repository.store_mac_address(saved_light["id"], normalized)
                result["mac_address"] = normalized
            suffix = result["mac_address"][-5:].replace(":", "") if result.get("mac_address") else result["ip_address"].split(".")[-1]
            result["suggested_name"] = f"WiZ light {suffix.upper()}"
        return sorted(results, key=lambda item: tuple(int(part) for part in item["ip_address"].split(".")))

    async def poll_light_statuses(self):
        return await self.controller.poll_statuses()
