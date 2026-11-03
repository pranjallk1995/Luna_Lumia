"""OpenRGB SDK client: drive PC RGB devices (keyboards, mice, motherboards) as Lumia lights.

OpenRGB runs on the PC that owns the devices and serves them over TCP (port 6742)
when started with ``--server``. Each OpenRGB controller becomes one Lumia light
whose whole surface shows a single color, so schemes, schedules, weather and
music treat it like any bulb.

The SDK protocol is spoken directly (no extra dependency). Lumia asks for
protocol version 0, whose controller layout is stable across OpenRGB releases.
Sockets are blocking and guarded by a thread lock because lights are driven from
two event loops (the HTTP server and the scene engine); calls run in a thread.
"""

import asyncio
import socket
import struct
import threading
from dataclasses import dataclass, field

MAGIC = b"ORGB"
HEADER = struct.Struct("<4sIII")  # magic, device index, packet id, payload size
REQUEST_CONTROLLER_COUNT = 0
REQUEST_CONTROLLER_DATA = 1
SET_CLIENT_NAME = 50
UPDATE_LEDS = 1050
SET_CUSTOM_MODE = 1100
DEFAULT_PORT = 6742
SCHEME = "openrgb://"


@dataclass(frozen=True)
class OpenRGBAddress:
    """Where one OpenRGB device lives: the PC's IP, the SDK port, and the device name."""

    host: str
    device: str
    port: int = DEFAULT_PORT

    def __str__(self) -> str:
        return f"{SCHEME}{self.host}:{self.port}/{self.device}"

    @classmethod
    def parse(cls, address: str) -> "OpenRGBAddress":
        if not address.startswith(SCHEME):
            raise ValueError(f"Not an OpenRGB address: {address}")
        location, _, device = address[len(SCHEME):].partition("/")
        host, _, port = location.partition(":")
        if not host or not device:
            raise ValueError(f"Incomplete OpenRGB address: {address}")
        return cls(host, device, int(port or DEFAULT_PORT))

    @staticmethod
    def is_openrgb(address: str) -> bool:
        return address.startswith(SCHEME)


@dataclass
class Controller:
    index: int
    name: str
    led_count: int
    first_color: tuple[int, int, int] | None = None


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
        for _ in range(zone_count):
            self.string()
            self.take("iIII")  # type, leds min/max/count
            (matrix_size,) = self.take("H")
            self.skip(matrix_size)
        (led_count,) = self.take("H")
        for _ in range(led_count):
            self.string()
            self.take("I")
        (color_count,) = self.take("H")
        first = self.take("BBBB")[:3] if color_count else None
        return Controller(index, name, led_count, first)


@dataclass
class OpenRGBConnection:
    """One TCP session with an OpenRGB server, reconnected on demand."""

    host: str
    port: int
    timeout: float
    sock: socket.socket | None = None
    controllers: dict[str, Controller] = field(default_factory=dict)
    direct: set[int] = field(default_factory=set)  # controllers already switched to Direct mode
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
        """Read until the reply to ``packet_id``, skipping notifications such as device-list updates."""
        while True:
            magic, _, received_id, size = HEADER.unpack(self._read_exact(HEADER.size))
            if magic != MAGIC:
                raise ConnectionError("Not an OpenRGB server")
            payload = self._read_exact(size)
            if received_id == packet_id:
                return payload

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
        self.controllers = controllers

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
        if name not in self.controllers:
            self._load_controllers()  # devices can be plugged in after Lumia connected
        if name not in self.controllers:
            raise LookupError(f"OpenRGB has no device named {name!r} on {self.host}")
        return self.controllers[name]

    def fill(self, name: str, rgb: tuple[int, int, int]) -> None:
        controller = self.controller(name)
        if not controller.led_count:
            raise LookupError(f"OpenRGB device {name!r} has no LEDs; size its zones in OpenRGB first")
        colors = bytes((*rgb, 0)) * controller.led_count
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
    # Last color/brightness per device, so a brightness-only or power-on command keeps its color.
    memory: dict[str, dict] = field(default_factory=dict)
    _guard: threading.Lock = field(default_factory=threading.Lock)

    def connection(self, address: OpenRGBAddress) -> OpenRGBConnection:
        key = (address.host, address.port)
        with self._guard:
            if key not in self.connections:
                self.connections[key] = OpenRGBConnection(address.host, address.port, self.timeout)
            return self.connections[key]

    @staticmethod
    def rgb(hex_color: str) -> tuple[int, int, int]:
        value = hex_color.lstrip("#")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    @staticmethod
    def white(kelvin: int) -> tuple[int, int, int]:
        from app.services.playback import ColorMath  # local import: services depend on integrations

        return ColorMath.kelvin_to_rgb(kelvin)

    def target_rgb(self, key: str, *, on, brightness, color, color_temp) -> tuple[int, int, int]:
        remembered = self.memory.setdefault(key, {"rgb": (255, 255, 255), "brightness": 100})
        if color is not None:
            remembered["rgb"] = self.rgb(color)
        elif color_temp is not None:
            remembered["rgb"] = self.white(color_temp)
        if brightness is not None:
            remembered["brightness"] = brightness
        if on is False or not any(remembered["rgb"]):
            return (0, 0, 0)
        scale = remembered["brightness"] / 100
        return tuple(round(channel * scale) for channel in remembered["rgb"])

    async def apply(
        self, address: str, *, on=None, brightness=None, color=None, color_temp=None
    ) -> None:
        if on is None and all(value is None for value in (brightness, color, color_temp)):
            return
        target = OpenRGBAddress.parse(address)
        rgb = self.target_rgb(
            str(target), on=on, brightness=brightness, color=color, color_temp=color_temp
        )
        connection = self.connection(target)
        await asyncio.wait_for(
            asyncio.to_thread(connection.run, lambda live: live.fill(target.device, rgb)),
            self.timeout + 1,
        )

    async def status(self, address: str) -> dict:
        """Confirm the device is served; its color stays as Lumia last set it."""
        target = OpenRGBAddress.parse(address)
        connection = self.connection(target)
        controller = await asyncio.wait_for(
            asyncio.to_thread(connection.run, lambda live: live.controller(target.device)),
            self.timeout + 1,
        )
        remembered = self.memory.setdefault(str(target), {"rgb": (255, 255, 255), "brightness": 100})
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


class LightRouter:
    """Send each light's commands to the adapter for its protocol (WiZ or OpenRGB)."""

    def __init__(self, wiz, openrgb: OpenRGBAdapter) -> None:
        self.wiz, self.openrgb = wiz, openrgb

    def _for(self, address: str):
        return self.openrgb if OpenRGBAddress.is_openrgb(address) else self.wiz

    async def apply(self, address: str, **state) -> None:
        await self._for(address).apply(address, **state)

    async def status(self, address: str) -> dict:
        return await self._for(address).status(address)


def light_address(light: dict) -> str:
    """The address a light's adapter understands: its IP, or an openrgb:// URL for PC devices."""
    if light.get("protocol") == "openrgb":
        return str(OpenRGBAddress(light["ip_address"], light["device"]))
    return light["ip_address"]

