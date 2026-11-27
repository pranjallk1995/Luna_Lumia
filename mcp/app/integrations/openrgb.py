"""OpenRGB SDK client: drive PC RGB devices (keyboards, mice, motherboards) as Lumia lights.

OpenRGB runs on the PC that owns the devices and serves them over TCP (port 6742)
when started with ``--server``. Each OpenRGB controller becomes one Lumia light
whose whole surface shows a single color, so schemes, schedules, weather and
music treat it like any bulb.

A light can also be part of a device: one zone (a motherboard's ARGB header) or a
range of LEDs within it, such as the LEDs of one banner in a chain of parts. Each
device keeps the colors last sent to all of its LEDs, so painting one part leaves
the others as they were, and each LED of a part can take its own color ("LED 1",
"LED 2", ... counted within the part).

The SDK protocol is spoken directly (no extra dependency). Lumia asks for
protocol version 0, whose controller layout is stable across OpenRGB releases.
Sockets are blocking and guarded by a thread lock because lights are driven from
two event loops (the HTTP server and the scene engine); calls run in a thread.
"""

import asyncio
import re
import socket
import struct
import threading
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode

from app.integrations.solid_color import SolidColors

MAGIC = b"ORGB"
HEADER = struct.Struct("<4sIII")  # magic, device index, packet id, payload size
REQUEST_CONTROLLER_COUNT = 0
REQUEST_CONTROLLER_DATA = 1
SET_CLIENT_NAME = 50
DEVICE_LIST_UPDATED = 100
UPDATE_LEDS = 1050
SET_CUSTOM_MODE = 1100
DEFAULT_PORT = 6742
SCHEME = "openrgb://"


LED_RANGE = re.compile(r"(\d{1,4})(?:-(\d{1,4}))?")
LED_NAME = re.compile(r"LED (\d{1,4})", re.IGNORECASE)


@dataclass(frozen=True)
class OpenRGBAddress:
    """Where one OpenRGB device lives: the PC's IP, the SDK port, and the device name.

    ``zone`` (a zone name, or its number counted from 1) and ``leds`` ("2-25", counted
    from 1 within the zone, or within the device without a zone) narrow it to a part.
    """

    host: str
    device: str
    port: int = DEFAULT_PORT
    zone: str | None = None
    leds: str | None = None

    def __str__(self) -> str:
        part = {key: value for key, value in (("zone", self.zone), ("leds", self.leds)) if value}
        return f"{SCHEME}{self.host}:{self.port}/{self.device}" + (f"#{urlencode(part)}" if part else "")

    @classmethod
    def parse(cls, address: str) -> "OpenRGBAddress":
        if not address.startswith(SCHEME):
            raise ValueError(f"Not an OpenRGB address: {address}")
        address, _, fragment = address.partition("#")
        location, _, device = address[len(SCHEME):].partition("/")
        host, _, port = location.partition(":")
        if not host or not device:
            raise ValueError(f"Incomplete OpenRGB address: {address}")
        part = {key: values[0] for key, values in parse_qs(fragment).items()}
        return cls(host, device, int(port or DEFAULT_PORT), part.get("zone"), part.get("leds"))

    @staticmethod
    def is_openrgb(address: str) -> bool:
        return address.startswith(SCHEME)


@dataclass
class Controller:
    index: int
    name: str
    led_count: int
    first_color: tuple[int, int, int] | None = None
    zones: list[tuple[str, int]] = field(default_factory=list)  # (name, LED count), in LED order
    colors: list[tuple[int, int, int]] = field(default_factory=list)

    def part(self, zone: str | None, leds: str | None) -> list[int]:
        """The device-wide LED indexes of a part: a zone (by name or number from 1), and a range within it."""
        start, count = 0, self.led_count
        if zone:
            names = [name.casefold() for name, _ in self.zones]
            if zone.isdigit() and 1 <= int(zone) <= len(self.zones):
                index = int(zone) - 1
            elif zone.casefold() in names:
                index = names.index(zone.casefold())
            else:
                choices = ", ".join(f"{n} ({name})" for n, (name, _) in enumerate(self.zones, start=1))
                raise LookupError(f"{self.name} has no zone {zone!r}; its zones are {choices}")
            start = sum(size for _, size in self.zones[:index])
            count = self.zones[index][1]
        if leds:
            match = LED_RANGE.fullmatch(leds.strip())
            if not match:
                raise ValueError(f"LEDs must be a number or a range such as 2-25, not {leds!r}")
            first, last = int(match[1]), int(match[2] or match[1])
            if not 1 <= first <= last <= count:
                raise LookupError(f"LEDs {leds} do not fit: this part of {self.name} has {count} LEDs")
            return list(range(start + first - 1, start + last))
        return list(range(start, start + count))


class ControllerParser:
    """Read the protocol-0 controller description, keeping what Lumia needs."""

    def __init__(self, data: bytes) -> None:
        self.data, self.offset = data, 0

    def take(self, fmt: str) -> tuple:
        values = struct.unpack_from("<" + fmt, self.data, self.offset)
        self.offset += struct.calcsize("<" + fmt)
        return values

    def string(self) -> str:
        (length,) = self.take("H")
        raw = self.data[self.offset : self.offset + length]
        self.offset += length
        return raw.rstrip(b"\x00").decode("utf-8", "replace")

    def skip(self, size: int) -> None:
        self.offset += size

    def parse(self, index: int) -> Controller:
        self.take("I")  # total size
        self.take("i")  # device type
        name = self.string()
        for _ in range(4):  # description, version, serial, location
            self.string()
        (mode_count,) = self.take("H")
        self.take("i")  # active mode
        for _ in range(mode_count):
            self.string()
            self.take("iIIIIIIII")  # value, flags, speed min/max, colors min/max, speed, direction, color mode
            (colors,) = self.take("H")
            self.skip(colors * 4)
        (zone_count,) = self.take("H")
        zones = []
        for _ in range(zone_count):
            zone_name = self.string()
            _, _, _, zone_leds = self.take("iIII")  # type, leds min/max/count
            (matrix_size,) = self.take("H")
            self.skip(matrix_size)
            zones.append((zone_name, zone_leds))
        (led_count,) = self.take("H")
        for _ in range(led_count):
            self.string()
            self.take("I")
        (color_count,) = self.take("H")
        colors = [self.take("BBBB")[:3] for _ in range(color_count)]
        return Controller(index, name, led_count, colors[0] if colors else None, zones, colors)


@dataclass
class OpenRGBConnection:
    """One TCP session with an OpenRGB server, reconnected on demand."""

    host: str
    port: int
    timeout: float
    sock: socket.socket | None = None
    controllers: dict[str, Controller] = field(default_factory=dict)
    direct: set[int] = field(default_factory=set)  # controllers already switched to Direct mode
    # Each device's colors as Lumia last sent them, so painting one part keeps the others.
    painted: dict[str, list[tuple[int, int, int]]] = field(default_factory=dict)
    stale: bool = False  # OpenRGB announced a device change, such as a resized zone
    lock: threading.Lock = field(default_factory=threading.Lock)

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None
        self.controllers, self.direct = {}, set()

    def _send(self, packet_id: int, device: int = 0, payload: bytes = b"") -> None:
        self.sock.sendall(HEADER.pack(MAGIC, device, packet_id, len(payload)) + payload)

    def _read_exact(self, size: int) -> bytes:
        chunks, remaining = [], size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise ConnectionError("OpenRGB closed the connection")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _reply(self, packet_id: int) -> bytes:
        """Read until the reply to ``packet_id``, noting device-list updates on the way."""
        while True:
            magic, _, received_id, size = HEADER.unpack(self._read_exact(HEADER.size))
            if magic != MAGIC:
                raise ConnectionError("Not an OpenRGB server")
            payload = self._read_exact(size)
            if received_id == packet_id:
                return payload
            if received_id == DEVICE_LIST_UPDATED:
                self.stale = True

    def _connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._send(SET_CLIENT_NAME, payload=b"Luna Lumia\x00")
        self._load_controllers()

    def _load_controllers(self) -> None:
        self._send(REQUEST_CONTROLLER_COUNT)
        (count,) = struct.unpack("<I", self._reply(REQUEST_CONTROLLER_COUNT)[:4])
        controllers = {}
        for index in range(count):
            self._send(REQUEST_CONTROLLER_DATA, index, struct.pack("<I", 0))
            controller = ControllerParser(self._reply(REQUEST_CONTROLLER_DATA)).parse(index)
            controllers.setdefault(controller.name, controller)
        if [c.index for c in controllers.values()] != [c.index for c in self.controllers.values()]:
            self.direct = set()  # indexes may have shifted
        self.controllers, self.stale = controllers, False

    def run(self, action):
        """Run ``action(self)`` under the lock, reconnecting once if the session dropped."""
        with self.lock:
            for attempt in (1, 2):
                try:
                    if self.sock is None:
                        self._connect()
                    return action(self)
                except (OSError, ConnectionError, struct.error):
                    self.close()
                    if attempt == 2:
                        raise

    def controller(self, name: str) -> Controller:
        if self.stale or name not in self.controllers:
            self._load_controllers()  # devices can be plugged in or resized after Lumia connected
        if name not in self.controllers:
            raise LookupError(f"OpenRGB has no device named {name!r} on {self.host}")
        return self.controllers[name]

    def fill(self, name: str, rgb: tuple[int, int, int]) -> None:
        self.paint(name, None, None, rgb)

    def paint(
        self, name: str, zone: str | None, leds: str | None, rgb: tuple[int, int, int],
        each: dict[int, tuple[int, int, int]] | None = None,
    ) -> None:
        """Color a device, or a part of it, ``rgb``; ``each`` colors single LEDs, counted from 1 within the part."""
        controller = self.controller(name)
        if not controller.led_count:
            raise LookupError(f"OpenRGB device {name!r} has no LEDs; size its zones in OpenRGB first")
        current = self.painted.get(name)
        if current is None or len(current) != controller.led_count:
            known = len(controller.colors) == controller.led_count
            current = list(controller.colors) if known else [(0, 0, 0)] * controller.led_count
        for number, index in enumerate(controller.part(zone, leds), start=1):
            current[index] = (each or {}).get(number, rgb)
        self.painted[name] = current
        colors = b"".join(bytes((*color, 0)) for color in current)
        payload = struct.pack("<H", controller.led_count) + colors
        if controller.index not in self.direct:  # Direct mode, so software colors show
            self._send(SET_CUSTOM_MODE, controller.index)
            self.direct.add(controller.index)
        self._send(UPDATE_LEDS, controller.index, struct.pack("<I", len(payload) + 4) + payload)
        # LED updates get no reply, so a round trip exposes a dropped session and run() resends.
        self._send(REQUEST_CONTROLLER_COUNT)
        self._reply(REQUEST_CONTROLLER_COUNT)


@dataclass
class OpenRGBAdapter:
    """Translate Lumia light states into whole-device colors on OpenRGB servers."""

    timeout: float = 3.0
    connections: dict[tuple[str, int], OpenRGBConnection] = field(default_factory=dict)
    colors: SolidColors = field(default_factory=SolidColors)
    _guard: threading.Lock = field(default_factory=threading.Lock)

    def connection(self, address: OpenRGBAddress) -> OpenRGBConnection:
        key = (address.host, address.port)
        with self._guard:
            if key not in self.connections:
                self.connections[key] = OpenRGBConnection(address.host, address.port, self.timeout)
            return self.connections[key]

    async def apply(
        self, address: str, *, on=None, brightness=None, color=None, color_temp=None, keys=None
    ) -> None:
        if on is None and keys is None and all(value is None for value in (brightness, color, color_temp)):
            return
        target = OpenRGBAddress.parse(address)
        rgb = self.colors.target(
            str(target), on=on, brightness=brightness, color=color, color_temp=color_temp
        )
        each = None
        if keys and on is not False:
            scale = self.colors.remembered(str(target))["brightness"] / 100
            each = {
                int(match[1]): tuple(round(channel * scale) for channel in self.colors.rgb(value))
                for name, value in keys.items()
                if (match := LED_NAME.fullmatch(name.strip()))
            }
        connection = self.connection(target)
        await asyncio.wait_for(
            asyncio.to_thread(connection.run, lambda live: live.paint(target.device, target.zone, target.leds, rgb, each)),
            self.timeout + 1,
        )

    async def leds(self, address: str) -> list[dict]:
        """A light's LEDs by name ("LED 1", ...), in chain order: x is the LED's number."""
        target = OpenRGBAddress.parse(address)
        connection = self.connection(target)
        controller = await asyncio.wait_for(
            asyncio.to_thread(connection.run, lambda live: live.controller(target.device)), self.timeout + 1
        )
        count = len(controller.part(target.zone, target.leds))
        return [{"key": f"LED {number}", "x": number, "y": 0} for number in range(1, count + 1)]

    async def status(self, address: str) -> dict:
        """Confirm the device is served; its color stays as Lumia last set it."""
        target = OpenRGBAddress.parse(address)
        connection = self.connection(target)
        controller = await asyncio.wait_for(
            asyncio.to_thread(connection.run, lambda live: live.controller(target.device)),
            self.timeout + 1,
        )
        controller.part(target.zone, target.leds)  # the zone or range must still exist
        remembered = self.colors.remembered(str(target))
        if controller.first_color and any(controller.first_color) and "seen" not in remembered:
            remembered.update(rgb=controller.first_color, seen=True)
        return {"mac_address": None}

    async def devices(self, host: str, port: int = DEFAULT_PORT) -> list[Controller]:
        """The devices an OpenRGB server offers, freshly read."""
        connection = self.connection(OpenRGBAddress(host, "-", port))

        def controllers(live: OpenRGBConnection) -> list[Controller]:
            live._load_controllers()
            return list(live.controllers.values())

        return await asyncio.wait_for(asyncio.to_thread(connection.run, controllers), self.timeout * 4)
