"""Luna Lumia use cases, independent of the HTTP and MCP transports."""

from __future__ import annotations

import asyncio
import logging
from ipaddress import IPv4Address
from datetime import date, datetime, time, timedelta
from time import monotonic
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from app.core import tenancy
from app.integrations.devices import WizDiscovery, WizLightAdapter
from app.integrations import icue as icue_integration
from app.integrations.icue import ICueAdapter
from app.integrations.openrgb import DEFAULT_PORT, OpenRGBAdapter
from app.integrations.router import light_address
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
from app.services.playback import BeatClock, ColorMath, SceneEngine, Step
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

if TYPE_CHECKING:
    from app.integrations.visia import VisiaImageTagger
    from app.services.music import MusicService


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
                    light_address(light),
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
                state = await self.adapter.status(light_address(light))
                reported = Validators.mac_address(state.pop("mac_address", None) or None)
                if light.get("mac_address") and reported and reported != light["mac_address"]:
                    return {
                        "light": light,
                        "ok": False,
                        "moved": True,
                        "error": f"A different bulb ({reported}) now answers at {light['ip_address']}",
                    }
                if self.engine and light["id"] in self.engine.playing():
                    state = {}  # a passing frame of a playing scheme, not the light's own state
                elif WizLightAdapter.same_on_bulb(light.get("color"), state.get("color")):
                    state["color"] = light["color"]
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
        tagger: VisiaImageTagger | None = None,
    ) -> None:
        self.room_images = room_images
        self.lights = lights
        self.collections = collections
        self.tagger = tagger

    def tagged(self, row: Row | None, image_url: str | None) -> Row | None:
        """Tag ``image_url`` "luna lumia" in Visia, noting the outcome on ``row``."""
        outcome = self.tagger.tag(image_url) if self.tagger and row else None
        if outcome:
            row["visia_tag"] = outcome
        return row

    def list_room_images(self) -> list[Row]:
        return self.room_images.list()

    def update_room_image(self, room_key: str, image_url: str) -> Row | None:
        return self.tagged(self.room_images.upsert(room_key, image_url), image_url)

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
        return self.tagged(light, image_url)

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
        assigned = self.tagged(self.lights.update_image(light_id, selected["image_url"]), selected["image_url"])
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
        assigned = self.tagged(self.collections.update_image(collection_id, selected["image_url"]), selected["image_url"])
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
        return self.tagged(collection, image_url)


class LightService:
    """Manage the light inventory and network discovery."""

    def __init__(
        self,
        lights: LightRepository,
        discovery: WizDiscovery,
        images: BackgroundImageService,
        openrgb: OpenRGBAdapter | None = None,
        icue: ICueAdapter | None = None,
    ) -> None:
        self.lights = lights
        self.discovery = discovery
        self.images = images
        self.openrgb = openrgb or OpenRGBAdapter()
        self.icue = icue or ICueAdapter()

    def list(self) -> list[Row]:
        return self.lights.list()

    def list_with_images(self) -> list[Row]:
        return self.images.decorate_lights(self.lights.list())

    def add(self, entry: LightCreate) -> Row | None:
        tenancy.require_owner("Adding lights")
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

    @staticmethod
    def pc_light_name(device: str) -> str:
        """A valid Lumia light name from a PC device name (letters, digits, spaces; 30 max)."""
        cleaned = " ".join("".join(c if c.isalnum() else " " for c in device).split())
        return (cleaned[:30].strip() or "PC RGB")

    async def discover_openrgb(self, host: str, port: int = DEFAULT_PORT) -> list[dict]:
        """List the devices an OpenRGB server on ``host`` offers, flagging those already added."""
        tenancy.require_owner("Finding PC devices")
        IPv4Address(host)
        controllers = await self.openrgb.devices(host, port)
        found = [(controller.name, controller.led_count) for controller in controllers]
        return self._pc_devices(host, "openrgb", found, port)

    async def discover_icue(self, host: str, port: int = icue_integration.DEFAULT_PORT) -> list[dict]:
        """List the Corsair devices iCUE offers through the bridge on ``host``."""
        tenancy.require_owner("Finding PC devices")
        IPv4Address(host)
        devices = await self.icue.devices(host, port)
        found = [(item["device"], item["led_count"]) for item in devices]
        return self._pc_devices(host, "icue", found, port)

    @staticmethod
    def same_device(first: str, second: str) -> bool:
        """Whether two programs' names look like one device: "K70 RGB PRO" and "Corsair K70 RGB PRO V2"."""
        words = [set(name.casefold().split()) for name in (first, second)]
        return words[0] <= words[1] or words[1] <= words[0]

    async def discover_pc(
        self, host: str, openrgb_port: int = DEFAULT_PORT, icue_port: int = icue_integration.DEFAULT_PORT
    ) -> dict:
        """Check a PC for OpenRGB and the iCUE bridge, and warn of devices both would drive."""
        tenancy.require_owner("Finding PC devices")
        IPv4Address(host)
        sources = {"openrgb": self.discover_openrgb(host, openrgb_port), "icue": self.discover_icue(host, icue_port)}
        found = await asyncio.gather(*sources.values(), return_exceptions=True)
        result: dict[str, Any] = {"ip_address": host, "devices": [], "warnings": []}
        for protocol, outcome in zip(sources, found):
            failed = isinstance(outcome, (OSError, LookupError, ValueError))
            if isinstance(outcome, BaseException) and not failed:
                raise outcome
            result[protocol] = {"available": not failed, "error": str(outcome) if failed else None}
            if not failed:
                result["devices"] += outcome
        for name, led_count in {d["device"]: d["led_count"] for d in result["devices"] if d["protocol"] == "openrgb"}.items():
            if not led_count:
                result["warnings"].append(f"{name} has no LEDs in OpenRGB. Size its zones there before adding it.")
            for other in result["devices"]:
                if other["protocol"] == "icue" and self.same_device(name, other["device"]):
                    result["warnings"].append(
                        f"{name} (OpenRGB) and {other['device']} (iCUE) look like one device. Add it "
                        "from one of them and turn off its detector in OpenRGB, or their lighting will fight."
                    )
        return result

    def _pc_devices(self, host: str, protocol: str, found: list[tuple[str, int]], port: int) -> list[dict]:
        configured = {
            light["device"]
            for light in self.lights.list()
            if light.get("protocol") == protocol and light["ip_address"] == host
        }
        return [
            {
                "ip_address": host,
                "device": name,
                "led_count": led_count,
                "protocol": protocol,
                "port": port,
                "configured": name in configured,
                "suggested_name": self.pc_light_name(name),
            }
            for name, led_count in found
        ]

    PC_PROTOCOLS = ("openrgb", "icue")
    PROBE_TIMEOUT = 0.75

    def pc_lights(self) -> list[Row]:
        return [light for light in self.lights.list() if light.get("protocol") in self.PC_PROTOCOLS]

    @classmethod
    def pc_port(cls, light: Row) -> int:
        return light.get("port") or (DEFAULT_PORT if light["protocol"] == "openrgb" else icue_integration.DEFAULT_PORT)

    @classmethod
    async def _listening(cls, host: str, port: int) -> bool:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), cls.PROBE_TIMEOUT)
        except (OSError, asyncio.TimeoutError):
            return False
        writer.close()
        return True

    async def _pc_device_names(self, protocol: str, port: int, host: str) -> set[str]:
        """The device names a PC offers on ``port``, or none if it does not answer."""
        try:
            if protocol == "openrgb":
                return {controller.name for controller in await self.openrgb.devices(host, port)}
            return {item["device"] for item in await self.icue.devices(host, port)}
        except (OSError, LookupError, ValueError, asyncio.TimeoutError):
            return set()

    def _allowed_pc_moves(self, moves: dict[int, str]) -> dict[int, str]:
        """The moves whose (new IP, device) is not held by a light that stays put."""
        saved = self.lights.list()
        by_id = {light["id"]: light for light in saved}
        held = {(light["ip_address"], light.get("device") or ""): light["id"] for light in saved}
        return {
            light_id: ip_address
            for light_id, ip_address in moves.items()
            if held.get((ip_address, by_id[light_id].get("device") or ""), light_id) in moves
        }

    async def find_moved_pc_lights(self, subnet: str | None = None) -> dict[str, Any]:
        """Find PCs whose IP changed by the RGB devices they offer, and move their lights.

        PC lights have no MAC, so a PC is recognised by its devices: every host on
        the /24 that listens on a saved PC light's port is asked for its devices,
        and a light moves to the one host offering its exact device name. With no
        ``subnet`` (like ``192.168.1``), the subnets the PC lights were last on are
        scanned.
        """
        tenancy.require_owner("Finding PC lights on the network")
        pc_lights = self.pc_lights()
        if subnet:
            octets = subnet.strip().removesuffix("/24").strip(".").split(".")
            if len(octets) not in (3, 4):
                raise ValueError("subnet must look like 192.168.1")
            prefix = ".".join(octets[:3])
            IPv4Address(f"{prefix}.0")
            prefixes = {prefix}
        else:
            prefixes = {light["ip_address"].rsplit(".", 1)[0] for light in pc_lights}
        sources = {(light["protocol"], self.pc_port(light)) for light in pc_lights}
        hosts = [f"{prefix}.{last}" for prefix in sorted(prefixes) for last in range(1, 255)]
        probes = [(protocol, port, host) for protocol, port in sorted(sources) for host in hosts]
        listening = await asyncio.gather(*(self._listening(host, port) for _, port, host in probes))
        answering = [probe for probe, up in zip(probes, listening) if up]
        names = await asyncio.gather(*(self._pc_device_names(*probe) for probe in answering))
        offered = dict(zip(answering, names))

        moves, unchanged, not_found, ambiguous = {}, [], [], []
        for light in pc_lights:
            protocol, port = light["protocol"], self.pc_port(light)
            matches = sorted(
                host for (kind, at, host), devices in offered.items()
                if kind == protocol and at == port and light.get("device") in devices
            )
            if light["ip_address"] in matches:
                unchanged.append(light["name"])
            elif len(matches) == 1:
                moves[light["id"]] = matches[0]
            elif matches:
                ambiguous.append({"name": light["name"], "hosts": matches})
            else:
                not_found.append(light["name"])
        allowed = self._allowed_pc_moves(moves)
        self.lights.relocate(allowed)
        by_id = {light["id"]: light for light in pc_lights}
        return {
            "scanned": sorted(f"{prefix}.0/24" for prefix in prefixes),
            "moved": [
                {"id": light_id, "name": by_id[light_id]["name"], "from": by_id[light_id]["ip_address"], "to": ip}
                for light_id, ip in allowed.items()
            ],
            "blocked": [by_id[light_id]["name"] for light_id in moves if light_id not in allowed],
            "unchanged": unchanged,
            "ambiguous": ambiguous,
            "not_found": not_found,
        }

    def move_pc_lights(self, old_host: str, new_host: str) -> list[Row]:
        """Point every PC light saved at ``old_host`` to ``new_host`` (the PC got a new IP)."""
        tenancy.require_owner("Moving PC lights")
        IPv4Address(old_host)
        IPv4Address(new_host)
        moving = {light["id"]: new_host for light in self.pc_lights() if light["ip_address"] == old_host}
        if not moving:
            raise NotFoundError(f"No PC lights are saved at {old_host}")
        if len(self._allowed_pc_moves(moving)) < len(moving):
            raise ValueError(f"{new_host} already has a light for one of these devices")
        self.lights.relocate(moving)
        return [light for light in self.lights.list() if light["id"] in moving]

    async def discover(self, broadcast_space: str = AppConfig.GLOBAL_BROADCAST) -> list[dict]:
        """Scan for lights, follow saved lights to new IPs, and flag configured ones."""
        tenancy.require_owner("Finding lights on the network")
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
        frames = self.engine.live()
        self.engine.stop(stopped)
        # A stopped light stays on its last frame, so that is its state now.
        for light_id in stopped:
            if light_id in frames:
                self.control.lights.update_state(light_id, **frames[light_id])
        return {"stopped_light_ids": stopped}

    def playing(self) -> dict[int, int]:
        return self.engine.playing()

    def live(self) -> dict[int, dict[str, Any]]:
        return self.engine.live()

    def play_beats(self, target_type: str, target_id: int | None, scene_id: int, clock: BeatClock) -> dict[str, Any]:
        """Pulse the target lights on a track's beats in a scheme's colors (a solid is one color)."""
        scene = self.get(scene_id)
        lights = self.control.resolve_targets(target_type, target_id)
        if scene["kind"] == "solid":
            palette = [Step(scene["color"], scene["color_temp"], scene["brightness"], 0, 0, "linear")]
        else:
            palette = Step.from_scene(scene, self.transitions.by_id())
        LOG.info("Pulsing scheme %r on the beats: lights %s", scene["name"], [light["id"] for light in lights])
        self.engine.play_beats(scene["id"], palette, clock, lights)
        for light in lights:
            self.control.lights.update_state(light["id"], on=True)
        return {"scene": scene["name"], "light_ids": [light["id"] for light in lights], "beats": True}


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
    """Manage recurring and one-time schedules and alarms, and run the ones that are due."""

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
        """Schedules with their time today, or on their date if one-time (HH:MM), soonest first."""
        today = datetime.now(self.location.zone).date()
        rows = self.schedules.list()
        for row in rows:
            at = self.time_on(row, row.get("run_date") or today)
            row["today_time"] = at.strftime("%H:%M") if at else None
        return sorted(rows, key=lambda row: (row["today_time"] is None, row["today_time"] or "", row["name"]))

    def get(self, schedule_id: int) -> Row:
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            raise NotFoundError("Schedule not found")
        return schedule

    def first_run_date(self, entry: ScheduleCreate) -> date | None:
        """The ``last_run_date`` a new or edited schedule starts with.

        A time that has already passed today waits for the next scheduled day. A
        one-time schedule must still be ahead, unless it is switched off (as it is
        once it has run).
        """
        if entry.time_mode != "time" and not self.location.get():
            raise ValueError("Set your location in the Schedules tab to use sunrise or sunset times")
        now = datetime.now(self.location.zone)
        if entry.run_date is not None:
            at = self.time_on(entry.model_dump(), entry.run_date)
            passed = entry.run_date < now.date() or (
                entry.run_date == now.date() and (at is None or at <= now.time())
            )
            if passed and entry.enabled:
                raise ValueError("That date and time has already passed; choose a later one")
            return None
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

    def reapply(self) -> None:
        """Apply the weather's scheme again on the next tick (after music let go of the lights)."""
        self.automation_settings.mark_applied(None)

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
        music: "MusicService",
    ) -> None:
        self.lights = lights
        self.collections = collections
        self.images = images
        self.control = control
        self.scenes = scenes
        self.transitions = transitions
        self.schedules = schedules
        self.weather = weather
        self.music = music
        # When each kind of scan may next run, after one that found nothing new.
        self.quiet_until: dict[str, float] = {}

    def decorate(self, schemes: list[Row]) -> list[Row]:
        """Mark each scheme with the weather slots and music moods it plays for."""
        return self.music.decorate(self.weather.decorate(schemes))

    # A switched-off bulb or PC should not cost a network scan on every refresh.
    RESCAN_COOLDOWN_SECONDS = 300.0

    def _scan_due(self, kind: str) -> bool:
        return monotonic() >= self.quiet_until.get(kind, 0.0)

    async def refresh_lights(self) -> list[dict[str, Any]]:
        """Read every bulb's state; if a known bulb moved, find its new IP and read again.

        Routers can hand bulbs new addresses. A known bulb (one with a saved MAC)
        that is silent, or whose IP now answers with another bulb's MAC, triggers
        a LAN scan that moves every light to the IP where its MAC answers. A silent
        PC light (OpenRGB or iCUE) has no MAC, so its PC is looked for on the LAN by
        the devices it offers instead. A scan that leaves its kind of light silent
        is not repeated for a few minutes: that light is probably switched off.
        """
        def silent(rows: list[dict[str, Any]]) -> dict[str, bool]:
            lights = [item["light"] for item in rows if not item["ok"]]
            return {
                "bulbs": any(light.get("mac_address") for light in lights),
                "pcs": any(light.get("protocol") in LightService.PC_PROTOCOLS for light in lights),
            }

        results = await self.control.poll_statuses()
        missing = silent(results)
        scans = {}
        if missing["bulbs"] and self._scan_due("bulbs"):
            scans["bulbs"] = self.lights.discover(self.lights.subnet_broadcast())
        if missing["pcs"] and tenancy.is_owner() and self._scan_due("pcs"):
            scans["pcs"] = self.lights.find_moved_pc_lights()
        if not scans:
            return results
        await asyncio.gather(*scans.values())
        results = await self.control.poll_statuses()
        missing = silent(results)
        for kind in scans:
            self.quiet_until[kind] = monotonic() + self.RESCAN_COOLDOWN_SECONDS if missing[kind] else 0.0
        return results

    def dashboard(self) -> dict[str, Any]:
        return {
            "location": self.schedules.location.today(),
            "lights": self.lights.list_with_images(),
            "rooms": self.collections.list_with_images("room"),
            "groups": self.collections.list_with_images("group"),
            "scenes": self.decorate(self.scenes.list()),
            "transitions": self.transitions.list(),
            "playing": {str(light_id): scene_id for light_id, scene_id in self.scenes.playing().items()},
            "live": {str(light_id): frame for light_id, frame in self.scenes.live().items()},
            "schedules": self.schedules.list(),
            "room_images": self.images.list_room_images(),
        }
