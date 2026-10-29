"""Luna Lumia use cases, independent of the HTTP and MCP transports."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.integrations.devices import WizDiscovery, WizLightAdapter
from app.core.errors import NotFoundError
from app.core.models import (
    CollectionKind,
    GroupCreate,
    LightCreate,
    LightState,
    LocationUpdate,
    SceneCreate,
    ScheduleCreate,
    TransitionCreate,
    Validators,
    WeatherAutomationUpdate,
    WeatherPeriod,
    WeatherReport,
)
from app.services.playback import ColorMath, SceneEngine, Step
from app.data.repositories import (
    CollectionRepository,
    LightRepository,
    LocationRepository,
    RoomImageRepository,
    Row,
    SceneRepository,
    ScheduleRepository,
    TransitionRepository,
    WeatherAutomationRepository,
    WeatherRepository,
    WeatherSchemeRepository,
)
from app.integrations.room_images import ImageScheme, RoomImageCatalog, RoomKeyDetector
from app.services.presets import WeatherPresets
from app.services.sun import SunCalculator
from app.core.config import AppConfig


# Uvicorn's logger, so these lines appear in the container log.
LOG = logging.getLogger("uvicorn.error")

class LightControlService:
    """Send states to physical lights and persist what they report back."""

    UNSCOPED_TARGETS = ("all", "on")

    def __init__(
        self,
        lights: LightRepository,
        adapter: WizLightAdapter | None = None,
        engine: SceneEngine | None = None,
    ) -> None:
        self.lights = lights
        self.adapter = adapter or WizLightAdapter()
        self.engine = engine

    def resolve_targets(self, target_type: str, target_id: int | None) -> list[Row]:
        if target_type not in self.UNSCOPED_TARGETS and target_id is None:
            raise ValueError("target_id is required")
        return self.lights.targets(target_type, target_id)

    def stop_sequences(self, lights: list[Row]) -> None:
        """A manual change takes a light out of any sequence it is playing."""
        if self.engine:
            self.engine.stop([light["id"] for light in lights])

    async def control(
        self, target_type: str, target_id: int | None, state: LightState
    ) -> list[dict[str, Any]]:
        """Apply ``state`` to "all", "on" (lights currently on), "light", or "group" targets."""
        targets = self.resolve_targets(target_type, target_id)
        self.stop_sequences(targets)
        color = state.color.upper() if state.color else None
        # A brightness/color/temperature command turns the bulb on (see the adapter),
        # so record that too instead of waiting for the next status poll.
        changes_light = any(v is not None for v in (state.brightness, state.color, state.color_temp))
        powered_on = state.on if state.on is not None else (True if changes_light else None)

        async def send(light: Row) -> Exception | None:
            try:
                await self.adapter.apply(
                    light["ip_address"],
                    on=state.on,
                    brightness=state.brightness,
                    color=state.color,
                    color_temp=state.color_temp,
                )
            except Exception as error:  # noqa: BLE001 - reported per light below
                return error
            return None

        # Every bulb gets its command at once, so an unreachable bulb costs one
        # timeout in total instead of one for each bulb queued behind it.
        failures = await asyncio.gather(*(send(light) for light in targets))
        results = []
        for light, error in zip(targets, failures):
            if error is None:
                saved = self.lights.update_state(
                    light["id"],
                    on=powered_on,
                    brightness=state.brightness,
                    color=color,
                    color_temp=state.color_temp,
                    reachable=True,
                )
                results.append({"light": saved, "ok": True})
            else:
                self.lights.update_state(light["id"], reachable=False)
                message = str(error) or (
                    "The bulb did not answer in time."
                    if isinstance(error, (TimeoutError, asyncio.TimeoutError))
                    else type(error).__name__
                )
                results.append({"light": light, "ok": False, "error": message})
        return results

    async def poll_statuses(self) -> list[dict[str, Any]]:
        """Read every light's current state from the bulb and save it (on demand).

        Routers can reassign addresses, so the bulb answering at a light's IP may
        be a different bulb. Its reported MAC is checked first; on a mismatch the
        light is reported as ``moved`` and its saved state is left untouched.
        """
        async def poll(light: Row) -> dict[str, Any]:
            try:
                state = await self.adapter.status(light["ip_address"])
                reported = Validators.mac_address(state.pop("mac_address", None) or None)
                if light.get("mac_address") and reported and reported != light["mac_address"]:
                    return {
                        "light": light,
                        "ok": False,
                        "moved": True,
                        "error": f"A different bulb ({reported}) now answers at {light['ip_address']}",
                    }
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

    @staticmethod
    def normalized_mac(value: str | None) -> str | None:
        try:
            return Validators.mac_address(value)
        except ValueError:
            return None

    def _follow_moved_lights(self, saved: list[Row], results: list[dict]) -> None:
        """Update saved lights whose bulb (matched by MAC) now answers at a new IP.

        DHCP can reshuffle addresses, so the MAC is the stable identity. A move
        is skipped if its new IP is held by a saved light that is not moving.
        """
        by_mac = {light["mac_address"]: light for light in saved if light.get("mac_address")}
        by_ip = {light["ip_address"]: light for light in saved}
        moves = {}
        for result in results:
            light = by_mac.get(result["mac_address"])
            if light and light["ip_address"] != result["ip_address"]:
                moves[light["id"]] = result["ip_address"]
                result["moved_from"] = light["ip_address"]
        blocked = {
            light_id
            for light_id, ip_address in moves.items()
            if (holder := by_ip.get(ip_address)) and holder["id"] not in moves
        }
        self.lights.relocate({key: ip for key, ip in moves.items() if key not in blocked})

    def _backfill_macs(self, saved: list[Row], results: list[dict]) -> None:
        """Record a MAC for a saved light that has none, unless another light owns it."""
        owned = {light["mac_address"] for light in saved if light.get("mac_address")}
        by_ip = {light["ip_address"]: light for light in saved}
        for result in results:
            light = by_ip.get(result["ip_address"])
            mac_address = result["mac_address"]
            if light and mac_address and not light.get("mac_address") and mac_address not in owned:
                self.lights.store_mac_address(light["id"], mac_address)
                owned.add(mac_address)

    def subnet_broadcast(self) -> str:
        """The /24 broadcast address most saved lights live on (directed scans cross Docker)."""
        prefixes = [light["ip_address"].rsplit(".", 1)[0] for light in self.lights.list()]
        if not prefixes:
            return AppConfig.GLOBAL_BROADCAST
        return f"{max(set(prefixes), key=prefixes.count)}.255"

    async def discover(self, broadcast_space: str = AppConfig.GLOBAL_BROADCAST) -> list[dict]:
        """Scan for lights, follow saved lights to new IPs, and flag configured ones."""
        results = await self.discovery.scan(broadcast_space)
        for result in results:
            result["mac_address"] = self.normalized_mac(result.get("mac_address"))
        self._follow_moved_lights(self.lights.list(), results)
        saved = self.lights.list()
        self._backfill_macs(saved, results)
        configured_ips = {light["ip_address"] for light in saved}
        for result in results:
            result["configured"] = result["ip_address"] in configured_ips
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


class TransitionService:
    """Manage reusable fades between sequence steps."""

    def __init__(self, transitions: TransitionRepository) -> None:
        self.transitions = transitions

    def list(self) -> list[Row]:
        return self.transitions.list()

    def by_id(self) -> dict[int, Row]:
        return {row["id"]: row for row in self.transitions.list()}

    def add(self, entry: TransitionCreate) -> Row | None:
        return self.transitions.add(entry)

    def update(self, transition_id: int, entry: TransitionCreate) -> Row:
        if transition_id in {row["id"] for row in self.list() if row["is_preset"]}:
            raise ValueError("Built-in transitions can't be edited")
        updated = self.transitions.update(transition_id, entry)
        if not updated:
            raise NotFoundError("Transition not found")
        return updated

    def delete(self, transition_id: int) -> None:
        if transition_id in {row["id"] for row in self.list() if row["is_preset"]}:
            raise ValueError("Built-in transitions can't be deleted")
        if not self.transitions.delete(transition_id):
            raise NotFoundError("Transition not found")


class SceneService:
    """Manage solid and sequence schemes and play them on lights."""

    def __init__(
        self,
        scenes: SceneRepository,
        transitions: TransitionService,
        control: LightControlService,
        engine: SceneEngine,
    ) -> None:
        self.scenes = scenes
        self.transitions = transitions
        self.control = control
        self.engine = engine

    @staticmethod
    def describe(scene: Row, transitions: dict[int, Row]) -> Row:
        """Add preview colors and, for sequences, the length of one pass."""
        if scene["kind"] == "solid":
            scene["preview_colors"] = [ColorMath.preview_hex(scene["color"], scene["color_temp"])]
            return scene
        steps = scene["steps"]
        scene["preview_colors"] = [
            ColorMath.preview_hex(step.get("color"), step.get("color_temp")) for step in steps
        ]
        scene["cycle_ms"] = sum(
            step.get("hold_ms", 0)
            + (transitions.get(step.get("transition_id")) or {}).get("duration_ms", 0)
            for step in steps
        )
        return scene

    def list(self) -> list[Row]:
        transitions = self.transitions.by_id()
        return [self.describe(scene, transitions) for scene in self.scenes.list()]

    def _known_transitions(self, entry: SceneCreate) -> dict[int, Row]:
        known = self.transitions.by_id()
        unknown = {step.transition_id for step in entry.steps} - set(known) - {None}
        if unknown:
            raise ValueError(f"Unknown transition id(s): {sorted(unknown)}")
        return known

    def add(self, entry: SceneCreate) -> Row | None:
        known = self._known_transitions(entry)
        return self.describe(self.scenes.add(entry), known)

    def update(self, scene_id: int, entry: SceneCreate) -> Row:
        """Replace a user scheme; a sequence that is playing restarts with the new steps."""
        if self.get(scene_id)["is_preset"]:
            raise ValueError("Built-in schemes can't be edited")
        known = self._known_transitions(entry)
        updated = self.scenes.update(scene_id, entry)
        if not updated:
            raise NotFoundError("Scene not found")
        playing_ids = {light_id for light_id, playing in self.engine.playing().items() if playing == scene_id}
        if playing_ids:
            lights = [light for light in self.control.lights.targets("all", None) if light["id"] in playing_ids]
            if updated["kind"] == "sequence":
                self.engine.play(scene_id, Step.from_scene(updated, known), updated["loops"], lights)
            else:
                self.engine.stop(list(playing_ids))
        return self.describe(updated, known)

    def get(self, scene_id: int) -> Row:
        scene = self.scenes.get(scene_id)
        if not scene:
            raise NotFoundError("Scene not found")
        return scene

    def delete(self, scene_id: int) -> None:
        if self.get(scene_id)["is_preset"]:
            raise ValueError("Built-in schemes can't be deleted")
        if not self.scenes.delete(scene_id):
            raise NotFoundError("Scene not found")

    async def apply(self, target_type: str, target_id: int | None, scene_id: int) -> dict[str, Any]:
        """Set a solid scheme, or start a sequence (replacing any already playing).

        Returns the scheme, the target, and the ids of the lights it was applied to.
        """
        scene = self.get(scene_id)
        lights = self.control.resolve_targets(target_type, target_id)
        summary = {
            "scene": scene["name"],
            "kind": scene["kind"],
            "target_type": target_type,
            "target_id": target_id,
            "light_ids": [light["id"] for light in lights],
        }
        LOG.info("Applying scheme %r to %s %s: lights %s", scene["name"], target_type, target_id, summary["light_ids"])
        if scene["kind"] == "solid":
            state = LightState(
                on=True,
                brightness=scene["brightness"],
                color=scene["color"],
                color_temp=scene["color_temp"],
            )
            results = await self.control.control(target_type, target_id, state)
            return {**summary, "playing": False, "results": results}
        steps = Step.from_scene(scene, self.transitions.by_id())
        self.engine.play(scene["id"], steps, scene["loops"], lights)
        for light in lights:
            self.control.lights.update_state(light["id"], on=True)
        return {**summary, "playing": True}

    def stop(self, target_type: str = "all", target_id: int | None = None) -> dict[str, Any]:
        lights = self.control.resolve_targets(target_type, target_id)
        playing = self.engine.playing()
        stopped = [light["id"] for light in lights if light["id"] in playing]
        self.engine.stop(stopped)
        return {"stopped_light_ids": stopped}

    def playing(self) -> dict[int, int]:
        return self.engine.playing()


class LocationService:
    """The saved location, and the sunrise/sunset times computed for it."""

    def __init__(self, locations: LocationRepository, zone: ZoneInfo) -> None:
        self.locations = locations
        self.zone = zone

    def get(self) -> Row | None:
        return self.locations.get()

    def save(self, entry: LocationUpdate) -> Row | None:
        return self.locations.save(entry)

    def sun_times(self, day: date) -> dict[str, datetime | None] | None:
        """Local sunrise and sunset on ``day``, or None when no location is saved."""
        location = self.get()
        if not location:
            return None
        return SunCalculator.times(day, location["latitude"], location["longitude"], self.zone)

    def today(self) -> dict[str, Any] | None:
        """Location plus today's sunrise/sunset as HH:MM (None when the sun does not rise/set)."""
        location = self.get()
        if not location:
            return None
        times = self.sun_times(datetime.now(self.zone).date())
        return {
            **location,
            **{event: moment.strftime("%H:%M") if moment else None for event, moment in times.items()},
        }


class ScheduleService:
    """Manage recurring schedules and alarms, and run the ones that are due."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        control: LightControlService,
        scenes: SceneService,
        location: LocationService,
    ) -> None:
        self.schedules = schedules
        self.control = control
        self.scenes = scenes
        self.location = location

    def time_on(self, schedule: Row, day: date) -> time | None:
        """When ``schedule`` runs on ``day``: its fixed time, or sunrise/sunset plus its offset.

        None means it cannot run that day (no saved location, or no sunrise/sunset).
        """
        if schedule["time_mode"] == "time":
            run_time = schedule["run_time"]
            return time.fromisoformat(run_time) if isinstance(run_time, str) else run_time
        sun = self.location.sun_times(day) or {}
        moment = sun.get(schedule["time_mode"])
        if moment is None:
            return None
        shifted = moment + timedelta(minutes=schedule["offset_minutes"])
        # An offset that crosses midnight is clamped to the same day.
        if shifted.date() != day:
            return time(0, 0) if shifted.date() < day else time(23, 59)
        return shifted.time().replace(second=0, microsecond=0)

    def list(self) -> list[Row]:
        """Schedules with their time today (HH:MM), soonest first."""
        today = datetime.now(self.location.zone).date()
        rows = self.schedules.list()
        for row in rows:
            at = self.time_on(row, today)
            row["today_time"] = at.strftime("%H:%M") if at else None
        return sorted(rows, key=lambda row: (row["today_time"] is None, row["today_time"] or "", row["name"]))

    def get(self, schedule_id: int) -> Row:
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            raise NotFoundError("Schedule not found")
        return schedule

    def first_run_date(self, entry: ScheduleCreate) -> date | None:
        """The ``last_run_date`` a new or edited schedule starts with.

        A time that has already passed today waits for the next scheduled day.
        """
        if entry.time_mode != "time" and not self.location.get():
            raise ValueError("Set your location in the Schedules tab to use sunrise or sunset times")
        now = datetime.now(self.location.zone)
        at = self.time_on(entry.model_dump(), now.date())
        already_passed = at is not None and at <= now.time() and now.weekday() in entry.weekdays
        return now.date() if already_passed else None

    def add(self, entry: ScheduleCreate) -> Row | None:
        return self.schedules.add(entry, self.first_run_date(entry))

    def update(self, schedule_id: int, entry: ScheduleCreate) -> Row:
        """Replace a schedule; its next run is worked out again from the new time."""
        updated = self.schedules.update(schedule_id, entry, self.first_run_date(entry))
        if not updated:
            raise NotFoundError("Schedule not found")
        return updated

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
        today = now.date()
        for schedule in self.schedules.pending(today, now.weekday()):
            at = self.time_on(schedule, today)
            if at is None or at > now.time():
                continue
            try:
                asyncio.run(self.execute(schedule))
            except Exception:
                continue
            self.schedules.mark_ran(schedule["id"], today)


class WeatherService:
    """Store each day's weather and play the scheme that matches it.

    A day's weather is a list of periods; each lasts until the next one starts
    (the first also covers the hours before it). Day and night follow sunrise
    and sunset at the saved location, or 06:00-18:00 without one.
    """

    DAY_START, DAY_END = time(6, 0), time(18, 0)

    def __init__(
        self,
        days: WeatherRepository,
        slots: WeatherSchemeRepository,
        automation: WeatherAutomationRepository,
        scenes: SceneService,
        location: LocationService,
    ) -> None:
        self.days = days
        self.slots = slots
        self.automation_settings = automation
        self.scenes = scenes
        self.location = location

    def now(self) -> datetime:
        return datetime.now(self.location.zone)

    def day_or_today(self, day: date | str | None) -> date:
        if day is None:
            return self.now().date()
        return date.fromisoformat(day) if isinstance(day, str) else day

    # Weather reports

    def record(self, report: WeatherReport) -> Row | None:
        return self.days.save(report)

    def get(self, day: date | str | None = None) -> Row:
        report = self.days.get(self.day_or_today(day))
        if not report:
            raise NotFoundError("No weather recorded for that day")
        return report

    def update_period(self, day: date | str | None, start: str, changes: dict[str, Any]) -> Row | None:
        """Change one period (matched by start time), or add it; other periods are kept.

        Creates the day's report if there is none yet.
        """
        day = self.day_or_today(day)
        start_time = time.fromisoformat(start).replace(second=0, microsecond=0)
        report = self.days.get(day) or {"periods": []}
        periods = [WeatherPeriod(**period) for period in report["periods"]]
        existing = next((period for period in periods if period.start == start_time), None)
        merged = {**(existing.model_dump() if existing else {}), **changes, "start": start_time}
        updated = WeatherPeriod(**merged)
        periods = [period for period in periods if period.start != start_time] + [updated]
        return self.days.save(
            WeatherReport(
                day=day, periods=periods, location=report.get("location"),
                summary=report.get("summary"), source=report.get("source"),
            )
        )

    def delete(self, day: date | str) -> None:
        if not self.days.delete(self.day_or_today(day)):
            raise NotFoundError("No weather recorded for that day")

    # Matching weather to schemes

    @staticmethod
    def period_at(report: Row, at: time) -> Row:
        periods = report["periods"]
        current = periods[0]
        for period in periods:
            if time.fromisoformat(period["start"]) <= at:
                current = period
        return current

    def daypart(self, moment: datetime) -> str:
        sun = self.location.sun_times(moment.date()) or {}
        sunrise, sunset = sun.get("sunrise"), sun.get("sunset")
        if sunrise and sunset:
            return "day" if sunrise <= moment < sunset else "night"
        return "day" if self.DAY_START <= moment.time() < self.DAY_END else "night"

    def slot_list(self) -> list[Row]:
        """Every (condition, daypart) slot with its scheme; empty slots fall back to the built-in."""
        presets = {row["name"]: row for row in self.scenes.scenes.list() if row["is_preset"]}
        saved = {(row["condition"], row["daypart"]): row for row in self.slots.list()}
        rows = []
        for condition, daypart in WeatherPresets.slots():
            built_in = presets.get(WeatherPresets.name(condition, daypart))
            row = saved.get((condition, daypart))
            if row and row["scene_id"] is not None:
                scheme = {"id": row["scene_id"], "name": row["scheme_name"], "kind": row["scheme_kind"]}
            elif built_in:
                scheme = {"id": built_in["id"], "name": built_in["name"], "kind": built_in["kind"]}
            else:
                scheme = None
            rows.append({
                "condition": condition,
                "daypart": daypart,
                "scheme": scheme,
                "is_built_in": bool(scheme and built_in and scheme["id"] == built_in["id"]),
                "built_in_scheme_id": built_in["id"] if built_in else None,
            })
        return rows

    def slot(self, condition: str, daypart: str) -> Row:
        return next(
            row for row in self.slot_list() if (row["condition"], row["daypart"]) == (condition, daypart)
        )

    def set_slot(self, condition: str, daypart: str, scene_id: int) -> Row:
        self.scenes.get(scene_id)
        self.slots.set(condition, daypart, scene_id)
        return self.slot(condition, daypart)

    def reset_slots(self, condition: str | None = None, daypart: str | None = None) -> list[Row]:
        """Point the matching slots (all when both are None) back at their built-in schemes."""
        for row in self.slot_list():
            if condition not in (None, row["condition"]) or daypart not in (None, row["daypart"]):
                continue
            self.slots.set(row["condition"], row["daypart"], row["built_in_scheme_id"])
        return self.slot_list()

    def decorate(self, schemes: list[Row]) -> list[Row]:
        """Add ``weather_slots`` (e.g. ["rain/night"]) to each scheme used for the weather."""
        used: dict[int, list[str]] = {}
        for row in self.slot_list():
            if row["scheme"]:
                used.setdefault(row["scheme"]["id"], []).append(f'{row["condition"]}/{row["daypart"]}')
        for scheme in schemes:
            scheme["weather_slots"] = used.get(scheme["id"], [])
        return schemes

    def current(self, moment: datetime | None = None) -> Row | None:
        """The weather now and the scheme for it, or None when today has no report."""
        moment = moment or self.now()
        report = self.days.get(moment.date())
        if not report or not report["periods"]:
            return None
        period = self.period_at(report, moment.time())
        daypart = self.daypart(moment)
        return {
            "day": moment.date().isoformat(),
            "time": moment.strftime("%H:%M"),
            "daypart": daypart,
            "condition": period["condition"],
            "period": period,
            "scheme": self.slot(period["condition"], daypart)["scheme"],
        }

    def today(self) -> Row:
        """Today's report (or None), what applies now, and the automation setting."""
        return {
            "report": self.days.get(self.now().date()),
            "now": self.current(),
            "automation": self.automation(),
        }

    async def apply_current(
        self, target_type: str = "all", target_id: int | None = None, moment: datetime | None = None
    ) -> Row:
        weather = self.current(moment)
        if weather is None:
            raise NotFoundError("No weather recorded for today; record it first")
        if weather["scheme"] is None:
            raise ValueError(f'No scheme for {weather["condition"]} by {weather["daypart"]}')
        applied = await self.scenes.apply(target_type, target_id, weather["scheme"]["id"])
        return {"weather": weather, **applied}

    # Automation

    def automation(self) -> Row:
        return self.automation_settings.get()

    def set_automation(self, entry: WeatherAutomationUpdate) -> Row:
        if entry.target_type in ("light", "group"):
            self.scenes.control.resolve_targets(entry.target_type, entry.target_id)
        return {**self.automation_settings.save(entry), "now": self.current()}

    @staticmethod
    def applied_key(weather: Row) -> str:
        return f'{weather["day"]}|{weather["condition"]}|{weather["daypart"]}|{weather["scheme"]["id"]}'

    def follow(self, moment: datetime) -> None:
        """Apply the matching scheme once each time the weather, day/night, or its scheme changes."""
        settings = self.automation()
        if not settings["enabled"]:
            return
        weather = self.current(moment)
        if weather is None or weather["scheme"] is None:
            return
        key = self.applied_key(weather)
        if key == settings["last_applied"]:
            return
        LOG.info("Weather is %s (%s); applying %r", weather["condition"], weather["daypart"], weather["scheme"]["name"])
        asyncio.run(self.scenes.apply(settings["target_type"], settings["target_id"], weather["scheme"]["id"]))
        self.automation_settings.mark_applied(key)


class LumiaService:
    """Facade grouping every Luna Lumia use case for the transport adapters."""

    def __init__(
        self,
        lights: LightService,
        collections: CollectionService,
        images: BackgroundImageService,
        control: LightControlService,
        scenes: SceneService,
        transitions: TransitionService,
        schedules: ScheduleService,
        weather: WeatherService,
    ) -> None:
        self.lights = lights
        self.collections = collections
        self.images = images
        self.control = control
        self.scenes = scenes
        self.transitions = transitions
        self.schedules = schedules
        self.weather = weather

    async def refresh_lights(self) -> list[dict[str, Any]]:
        """Read every bulb's state; if a known bulb moved, find its new IP and read again.

        Routers can hand bulbs new addresses. A known bulb (one with a saved MAC)
        that is silent, or whose IP now answers with another bulb's MAC, triggers
        a LAN scan that moves every light to the IP where its MAC answers.
        """
        results = await self.control.poll_statuses()
        if not any(not item["ok"] and item["light"].get("mac_address") for item in results):
            return results
        await self.lights.discover(self.lights.subnet_broadcast())
        return await self.control.poll_statuses()

    def dashboard(self) -> dict[str, Any]:
        return {
            "location": self.schedules.location.today(),
            "lights": self.lights.list_with_images(),
            "rooms": self.collections.list_with_images("room"),
            "groups": self.collections.list_with_images("group"),
            "scenes": self.weather.decorate(self.scenes.list()),
            "transitions": self.transitions.list(),
            "playing": {str(light_id): scene_id for light_id, scene_id in self.scenes.playing().items()},
            "schedules": self.schedules.list(),
            "room_images": self.images.list_room_images(),
        }
