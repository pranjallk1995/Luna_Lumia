"""Luna Lumia use cases, independent of the HTTP and MCP transports."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from .devices import GLOBAL_BROADCAST, WizDiscovery, WizLightAdapter
from .errors import NotFoundError
from .models import (
    CollectionKind,
    GroupCreate,
    LightCreate,
    LightState,
    SceneCreate,
    ScheduleCreate,
    Validators,
)
from .repositories import (
    CollectionRepository,
    LightRepository,
    RoomImageRepository,
    Row,
    SceneRepository,
    ScheduleRepository,
)
from .room_images import ImageScheme, RoomImageCatalog, RoomKeyDetector


class LightControlService:
    """Send states to physical lights and persist what they report back."""

    def __init__(self, lights: LightRepository, adapter: WizLightAdapter | None = None) -> None:
        self.lights = lights
        self.adapter = adapter or WizLightAdapter()

    async def control(
        self, target_type: str, target_id: int | None, state: LightState
    ) -> list[dict[str, Any]]:
        if target_type != "all" and target_id is None:
            raise ValueError("target_id is required")
        color = state.color.upper() if state.color else None
        results = []
        for light in self.lights.targets(target_type, target_id):
            try:
                await self.adapter.apply(
                    light["ip_address"], on=state.on, brightness=state.brightness, color=state.color
                )
                saved = self.lights.update_state(
                    light["id"], on=state.on, brightness=state.brightness, color=color, reachable=True
                )
                results.append({"light": saved, "ok": True})
            except Exception as error:
                self.lights.update_state(light["id"], reachable=False)
                results.append({"light": light, "ok": False, "error": str(error)})
        return results

    async def poll_statuses(self) -> list[dict[str, Any]]:
        async def poll(light: Row) -> dict[str, Any]:
            try:
                state = await self.adapter.status(light["ip_address"])
                saved = self.lights.update_state(light["id"], **state, reachable=True)
                return {"light": saved, "ok": True}
            except Exception as error:
                saved = self.lights.update_state(light["id"], reachable=False)
                return {"light": saved or light, "ok": False, "error": str(error)}

        return await asyncio.gather(*(poll(light) for light in self.lights.targets("all", None)))


class BackgroundImageService:
    """Resolve, infer, and store room-image backgrounds for lights and collections."""

    def __init__(
        self,
        room_images: RoomImageRepository,
        lights: LightRepository,
        collections: CollectionRepository,
    ) -> None:
        self.room_images = room_images
        self.lights = lights
        self.collections = collections

    def list_room_images(self) -> list[Row]:
        return self.room_images.list()

    def update_room_image(self, room_key: str, image_url: str) -> Row | None:
        return self.room_images.upsert(room_key, image_url)

    def catalog(self) -> RoomImageCatalog:
        return RoomImageCatalog(self.room_images.list())

    def _required_catalog(self) -> RoomImageCatalog:
        catalog = self.catalog()
        if not catalog:
            raise ValueError("No room images are configured")
        return catalog

    @staticmethod
    def collection_room_key(name: str, light_names: list[str]) -> str:
        return (
            RoomKeyDetector.detect(name)
            or RoomKeyDetector.for_member_names(light_names)
            or RoomKeyDetector.FALLBACK
        )

    def decorate_lights(self, lights: list[Row]) -> list[Row]:
        """Attach each light's detected room and effective card image."""
        catalog = self.catalog()
        for light in lights:
            light["room_key"] = RoomKeyDetector.for_name(light["name"])
            light["effective_image_url"] = light.get("background_image_url") or catalog.url_for(
                light["room_key"]
            )
        return lights

    def decorate_collections(self, collections: list[Row]) -> list[Row]:
        """Attach each room/group's detected room and effective card image."""
        catalog = self.catalog()
        for collection in collections:
            collection["room_key"] = self.collection_room_key(
                collection["name"], collection["light_names"]
            )
            collection["effective_image_url"] = collection.get(
                "background_image_url"
            ) or catalog.url_for(collection["room_key"])
        return collections

    @staticmethod
    def _describe(assigned: Row, selected: Row, room_key: str, source: str) -> Row:
        assigned["inferred_room_key"] = room_key
        assigned["image_scheme"] = ImageScheme.key(selected["image_url"])
        assigned["effective_image_url"] = selected["image_url"]
        assigned["inference_source"] = source
        return assigned

    def set_light_image(self, light_id: int, image_url: str | None) -> Row:
        light = self.lights.update_image(light_id, image_url)
        if not light:
            raise NotFoundError("Light not found")
        return light

    def infer_light_image(self, light_id: int, room_name: str | None = None) -> Row:
        light = self.lights.get(light_id)
        if not light:
            raise NotFoundError("Light not found")
        catalog = self._required_catalog()
        supplied_name = (room_name or "").strip()
        room_key = RoomKeyDetector.for_name(supplied_name or light["name"])
        scheme_counts = catalog.scheme_counts()
        existing_scheme = ImageScheme.key(light.get("background_image_url"))
        preferred_scheme = (
            existing_scheme
            if existing_scheme in scheme_counts
            else scheme_counts.most_common(1)[0][0]
        )
        selected = catalog.select(room_key, preferred_scheme)
        assigned = self.lights.update_image(light_id, selected["image_url"])
        source = "room_name" if supplied_name else "light_name"
        return self._describe(assigned, selected, room_key, source)

    def apply_light_image(
        self, light_id: int, image_url: str | None, room_name: str | None = None
    ) -> Row:
        """Store an explicit URL, or infer one when no URL is supplied."""
        if image_url is None:
            return self.infer_light_image(light_id, room_name)
        return self.set_light_image(light_id, image_url)

    def infer_collection_image(self, collection_id: int, room_name: str | None = None) -> Row:
        collection = self.collections.get(collection_id)
        if not collection:
            raise NotFoundError("Room/group not found")
        catalog = self._required_catalog()
        supplied_name = (room_name or "").strip()
        room_key = RoomKeyDetector.detect(supplied_name or collection["name"])
        source = "room_name"
        if room_key is None:
            light_names = collection["light_names"]
            room_key = RoomKeyDetector.for_member_names(light_names) or RoomKeyDetector.FALLBACK
            source = "light_name" if light_names else "fallback"
        scheme_counts = catalog.scheme_counts(
            [
                *collection["light_image_urls"],
                *(item["background_image_url"] for item in self.collections.list()),
            ]
        )
        preferred_scheme = ImageScheme.key(collection.get("background_image_url")) or (
            scheme_counts.most_common(1)[0][0] if scheme_counts else None
        )
        selected = catalog.select(room_key, preferred_scheme)
        assigned = self.collections.update_image(collection_id, selected["image_url"])
        assigned["light_ids"] = collection["light_ids"]
        return self._describe(assigned, selected, room_key, source)

    def apply_collection_image(
        self, collection_id: int, image_url: str | None, room_name: str | None = None
    ) -> Row:
        if image_url is None:
            return self.infer_collection_image(collection_id, room_name)
        collection = self.collections.update_image(collection_id, image_url)
        if not collection:
            raise NotFoundError("Room/group not found")
        return collection


class LightService:
    """Manage the light inventory and network discovery."""

    def __init__(
        self,
        lights: LightRepository,
        discovery: WizDiscovery,
        images: BackgroundImageService,
    ) -> None:
        self.lights = lights
        self.discovery = discovery
        self.images = images

    def list(self) -> list[Row]:
        return self.lights.list()

    def list_with_images(self) -> list[Row]:
        return self.images.decorate_lights(self.lights.list())

    def add(self, entry: LightCreate) -> Row | None:
        return self.lights.add(entry)

    def rename(self, light_id: int, name: str) -> Row:
        light = self.lights.rename(light_id, name)
        if not light:
            raise NotFoundError("Light not found")
        return light

    def delete(self, light_id: int) -> None:
        if not self.lights.delete(light_id):
            raise NotFoundError("Light not found")

    @staticmethod
    def suggested_name(result: dict) -> str:
        mac_address = result.get("mac_address")
        suffix = (
            mac_address[-5:].replace(":", "")
            if mac_address
            else result["ip_address"].split(".")[-1]
        )
        return f"WiZ light {suffix.upper()}"

    async def discover(self, broadcast_space: str = GLOBAL_BROADCAST) -> list[dict]:
        """Scan for lights, flag configured ones, and backfill their MAC addresses."""
        configured = {light["ip_address"]: light for light in self.lights.list()}
        results = await self.discovery.scan(broadcast_space)
        for result in results:
            saved_light = configured.get(result["ip_address"])
            result["configured"] = saved_light is not None
            if (
                saved_light
                and result.get("mac_address")
                and saved_light.get("mac_address") != result["mac_address"]
            ):
                normalized = Validators.mac_address(result["mac_address"])
                self.lights.store_mac_address(saved_light["id"], normalized)
                result["mac_address"] = normalized
            result["suggested_name"] = self.suggested_name(result)
        return sorted(
            results,
            key=lambda item: tuple(int(part) for part in item["ip_address"].split(".")),
        )


class CollectionService:
    """Manage rooms (one per light) and groups (overlapping) and their members."""

    KINDS = ("room", "group")

    def __init__(self, collections: CollectionRepository, images: BackgroundImageService) -> None:
        self.collections = collections
        self.images = images

    @classmethod
    def _validate_kind(cls, kind: str) -> None:
        if kind not in cls.KINDS:
            raise ValueError("Collection kind must be room or group")

    def list_with_images(self, kind: CollectionKind | None = None) -> list[Row]:
        return self.images.decorate_collections(self.collections.list(kind))

    def get(self, collection_id: int, kind: CollectionKind) -> Row:
        collection = self.collections.get(collection_id, kind)
        if not collection:
            raise NotFoundError(f"{kind.title()} not found")
        return collection

    def _ensure_room_free(self, light_ids: list[int]) -> None:
        conflicts = self.collections.room_conflicts(light_ids)
        if conflicts:
            details = ", ".join(
                f'{item["light_name"]} ({item["room_name"]})' for item in conflicts
            )
            raise ValueError(f"Already assigned to a room: {details}")

    def create(self, entry: GroupCreate, kind: CollectionKind) -> Row:
        self._validate_kind(kind)
        if kind == "room":
            self._ensure_room_free(entry.light_ids)
        collection_id = self.collections.add(entry, kind)
        if kind == "room":
            return self.images.infer_collection_image(collection_id)
        return self.collections.get(collection_id)

    def rename(self, collection_id: int, kind: CollectionKind, name: str) -> Row:
        self.get(collection_id, kind)
        if not self.collections.rename(collection_id, name):
            raise NotFoundError(f"{kind.title()} not found")
        return self.images.infer_collection_image(collection_id)

    def add_members(self, collection_id: int, kind: CollectionKind, light_ids: list[int]) -> Row:
        self.get(collection_id, kind)
        if kind == "room":
            self._ensure_room_free(light_ids)
        self.collections.add_members(collection_id, light_ids, kind)
        return self.get(collection_id, kind)

    def remove_member(self, collection_id: int, kind: CollectionKind, light_id: int) -> None:
        self.get(collection_id, kind)
        if not self.collections.remove_member(collection_id, light_id):
            raise NotFoundError("Light is not a member")

    def delete(self, collection_id: int, kind: CollectionKind) -> None:
        if not self.collections.delete(collection_id, kind):
            raise NotFoundError(f"{kind.title()} not found")


class SceneService:
    """Manage saved color schemes and apply them to lights."""

    def __init__(self, scenes: SceneRepository, control: LightControlService) -> None:
        self.scenes = scenes
        self.control = control

    def list(self) -> list[Row]:
        return self.scenes.list()

    def add(self, entry: SceneCreate) -> Row | None:
        return self.scenes.add(entry)

    def delete(self, scene_id: int) -> None:
        if not self.scenes.delete(scene_id):
            raise NotFoundError("Scene not found")

    async def apply(self, target_type: str, target_id: int | None, scene_id: int) -> list[dict]:
        scene = self.scenes.get(scene_id)
        if not scene:
            raise NotFoundError("Scene not found")
        state = LightState(on=True, brightness=scene["brightness"], color=scene["color"])
        return await self.control.control(target_type, target_id, state)


class ScheduleService:
    """Manage recurring schedules and alarms, and run the ones that are due."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        control: LightControlService,
        scenes: SceneService,
    ) -> None:
        self.schedules = schedules
        self.control = control
        self.scenes = scenes

    def list(self) -> list[Row]:
        return self.schedules.list()

    def add(self, entry: ScheduleCreate) -> Row | None:
        return self.schedules.add(entry)

    def delete(self, schedule_id: int) -> None:
        if not self.schedules.delete(schedule_id):
            raise NotFoundError("Schedule not found")

    async def execute(self, schedule: Row) -> None:
        target_type, target_id = schedule["target_type"], schedule["target_id"]
        if schedule["action"] == "scene":
            await self.scenes.apply(target_type, target_id, schedule["scene_id"])
        else:
            await self.control.control(
                target_type, target_id, LightState(on=schedule["action"] == "on")
            )

    def run_due(self, now: datetime) -> None:
        """Run each schedule due today once; failures are retried next tick."""
        for schedule in self.schedules.due(now.date(), now.weekday(), now.time()):
            try:
                asyncio.run(self.execute(schedule))
            except Exception:
                continue
            self.schedules.mark_ran(schedule["id"], now.date())


class LumiaService:
    """Facade grouping every Luna Lumia use case for the transport adapters."""

    def __init__(
        self,
        lights: LightService,
        collections: CollectionService,
        images: BackgroundImageService,
        control: LightControlService,
        scenes: SceneService,
        schedules: ScheduleService,
    ) -> None:
        self.lights = lights
        self.collections = collections
        self.images = images
        self.control = control
        self.scenes = scenes
        self.schedules = schedules

    def dashboard(self) -> dict[str, Any]:
        return {
            "lights": self.lights.list_with_images(),
            "rooms": self.collections.list_with_images("room"),
            "groups": self.collections.list_with_images("group"),
            "scenes": self.scenes.list(),
            "schedules": self.schedules.list(),
            "room_images": self.images.list_room_images(),
        }
