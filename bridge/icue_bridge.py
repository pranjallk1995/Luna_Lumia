"""Bridge between Luna Lumia and Corsair iCUE. Runs on the Windows PC that runs iCUE.

iCUE's SDK only works on the same machine, while Lumia runs in Docker, so this
small HTTP server takes whole-device colors from Lumia and hands them to iCUE.
It holds exclusive lighting control while it runs, so iCUE's own effects stay
hidden; stop the bridge and iCUE's lighting returns.

Needs the ``cuesdk`` package and a token (at least 32 characters) in
``icue_token.txt`` beside this file, matching this PC's token on the Lumia side.
``install.ps1`` sets all of this up. ``icue_bridge.json`` beside this file is optional:

    {"bind": "0.0.0.0", "port": 6743, "device_types": ["keyboard", "mouse"]}

``device_types`` picks what the bridge controls, from the names in DEVICE_TYPES. Leave out
anything another program drives; iCUE also lists ASUS boards, which OpenRGB usually drives.

    GET /devices                    -> [{"device": name, "led_count": n}, ...]
    PUT /devices/<name>/color       {"rgb": [r, g, b]}
    GET /devices/<name>/keys        -> [{"key": "W", "x": x, "y": y}, ...]  every LED, by name
    PUT /devices/<name>/keys        {"default": [r, g, b] or null, "keys": {"W": [r, g, b], ...}}

A keyboard's LEDs are named after their keys (``Escape``, ``W``, ``Space``, ``Keypad7``), from
iCUE's key IDs; other LEDs are named by their group and number (``Mouse 1``). ``x`` and ``y``
are the LED's center in iCUE's layout units from the device's top left, so patterns can follow rows,
columns, or distance. Keys left out keep their color, or take ``default`` when it is given.
"""

import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass
from functools import reduce
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from operator import or_
from pathlib import Path
from urllib.parse import unquote

ALPHA = 255
MAX_BODY_BYTES = 1024
MAX_KEYS_BODY_BYTES = 64 * 1024  # a color for each of a full keyboard's keys
DEVICE_TYPES = {
    "keyboard": "CDT_Keyboard",
    "mouse": "CDT_Mouse",
    "mousemat": "CDT_Mousemat",
    "headset": "CDT_Headset",
    "headset_stand": "CDT_HeadsetStand",
    "fan_led_controller": "CDT_FanLedController",
    "led_controller": "CDT_LedController",
    "memory_module": "CDT_MemoryModule",
    "cooler": "CDT_Cooler",
    "motherboard": "CDT_Motherboard",
    "graphics_card": "CDT_GraphicsCard",
    "touchbar": "CDT_Touchbar",
    "game_controller": "CDT_GameController",
}

log = logging.getLogger("icue_bridge")


def led_name(sdk_types, luid: int) -> str:
    """A keyboard key's name ("W", "Space"), or another LED's group and number ("Mouse 1")."""
    group, value = luid >> 16, luid & 0xFFFF
    groups = getattr(getattr(sdk_types, "CorsairLedGroup", None), "_reverse_map_", {})
    keys = getattr(getattr(sdk_types, "CorsairLedId_Keyboard", None), "_reverse_map_", {})
    group_name = groups.get(group, f"CLG_{group}")
    if group_name == "CLG_Keyboard" and value in keys:
        return keys[value].removeprefix("CLK_")
    return f"{group_name.removeprefix('CLG_')} {value}"


@dataclass(frozen=True)
class BridgeConfig:
    bind: str = "0.0.0.0"
    port: int = 6743
    device_types: tuple[str, ...] = ("keyboard", "mouse")

    @classmethod
    def load(cls, path: Path) -> "BridgeConfig":
        """Read the optional settings file, refusing anything it does not understand."""
        if not path.exists():
            return cls()
        settings = json.loads(path.read_text())
        unknown = set(settings) - {"bind", "port", "device_types"}
        if unknown:
            raise ValueError(f"Unknown settings in {path.name}: {sorted(unknown)}")
        config = cls(
            settings.get("bind", cls.bind),
            settings.get("port", cls.port),
            tuple(settings.get("device_types", cls.device_types)),
        )
        bad_types = set(config.device_types) - set(DEVICE_TYPES)
        if bad_types or not config.device_types:
            raise ValueError(f"device_types must come from {sorted(DEVICE_TYPES)}")
        if not isinstance(config.port, int) or not 1 <= config.port <= 65535:
            raise ValueError("port must be from 1 to 65535")
        return config


class ICueUnavailable(RuntimeError):
    """iCUE is not running, or refused the SDK session."""


class ICueLights:
    """Whole-device colors through the iCUE SDK, surviving iCUE restarts."""

    def __init__(self, sdk, sdk_types, device_types=BridgeConfig.device_types) -> None:
        self.sdk, self.types = sdk, sdk_types
        kinds = sdk_types.CorsairDeviceType
        self.device_mask = reduce(or_, (getattr(kinds, DEVICE_TYPES[name]) for name in device_types))
        self.lock = threading.Lock()
        self.connected = False
        self.devices: dict[str, list] = {}  # model -> [device id, LED ids]
        self.layouts: dict[str, list[dict]] = {}  # model -> [{"key", "id", "x", "y"}, ...]
        self.controlled: set[str] = set()  # iCUE refuses a second request for the same device
        self.colors: dict[str, tuple[int, int, int]] = {}
        self.key_colors: dict[str, dict[int, tuple[int, int, int]]] = {}  # model -> LED id -> color, for per-key patterns
        # iCUE can list no devices for a moment after a session opens.
        self.takeover_attempts, self.takeover_delay_seconds = 30, 1.0

    def start(self) -> None:
        error = self.sdk.connect(self.on_state_changed)
        if error != self.types.CorsairError.CE_Success:
            raise ICueUnavailable(f"Could not start the iCUE session: {error}")

    def on_state_changed(self, event) -> None:
        log.info("iCUE session: %s", event.state)
        connected = event.state == self.types.CorsairSessionState.CSS_Connected
        # SDK calls are not allowed inside its callback.
        threading.Thread(target=self.sync, args=(connected,), daemon=True).start()

    def sync(self, connected: bool) -> None:
        with self.lock:
            self.connected = connected
            self.devices, self.controlled = {}, set()
        if connected:
            self._take_over()

    def _take_over(self) -> None:
        """Retake control after a session opens and show what Lumia last set, even with no scheme playing."""
        for _ in range(self.takeover_attempts):
            with self.lock:
                if not self.connected:
                    return
                try:
                    self._load_devices()
                    for name, rgb in self.colors.items():
                        if name in self.devices:
                            self._paint(name, rgb)
                    for name, colors in self.key_colors.items():
                        if name in self.devices:
                            self._paint_leds(name, colors)
                    if self.devices:
                        return
                except ICueUnavailable as error:  # a later attempt or Lumia's next command tries again
                    log.warning("Could not take over iCUE's devices: %s", error)
            time.sleep(self.takeover_delay_seconds)

    def _check(self, error) -> None:
        if error != self.types.CorsairError.CE_Success:
            raise ICueUnavailable(f"iCUE refused the request: {error}")

    def _load_devices(self) -> None:
        wanted = self.types.CorsairDeviceFilter(device_type_mask=self.device_mask)
        found, error = self.sdk.get_devices(wanted)
        self._check(error)
        devices, layouts = {}, {}
        for device in found:
            leds, error = self.sdk.get_led_positions(device.device_id)
            self._check(error)
            layouts[device.model] = [
                {"key": led_name(self.types, led.id), "id": led.id,
                 "x": round(getattr(led, "cx", 0.0), 1), "y": round(getattr(led, "cy", 0.0), 1)}
                for led in leds
            ]
            if device.device_id not in self.controlled:
                self._check(
                    self.sdk.request_control(
                        device.device_id, self.types.CorsairAccessLevel.CAL_ExclusiveLightingControl
                    )
                )
                self.controlled.add(device.device_id)
            devices[device.model] = [device.device_id, [led.id for led in leds]]
        self.devices, self.layouts = devices, layouts
        log.info("iCUE devices: %s", {name: len(item[1]) for name, item in self.devices.items()})

    def _ready(self) -> None:
        if not self.connected:
            raise ICueUnavailable("iCUE is not connected")
        if not self.devices:  # devices can show up after the session opens
            self._load_devices()

    def _paint(self, name: str, rgb: tuple[int, int, int]) -> None:
        device_id, led_ids = self.devices[name]
        colors = [self.types.CorsairLedColor(led_id, *rgb, ALPHA) for led_id in led_ids]
        self._check(self.sdk.set_led_colors(device_id, colors))

    def _paint_leds(self, name: str, colors: dict[int, tuple[int, int, int]]) -> None:
        device_id, _ = self.devices[name]
        self._check(self.sdk.set_led_colors(
            device_id, [self.types.CorsairLedColor(led_id, *rgb, ALPHA) for led_id, rgb in colors.items()]
        ))

    def _device(self, name: str) -> None:
        self._ready()
        if name not in self.devices:
            self._load_devices()  # plugged in after the bridge connected
        if name not in self.devices:
            raise LookupError(f"iCUE has no device named {name!r}")

    def keys(self, name: str) -> list[dict]:
        """Every LED of a device by name, with its position in iCUE's layout units."""
        with self.lock:
            self._device(name)
            return [{"key": led["key"], "x": led["x"], "y": led["y"]} for led in self.layouts[name]]

    def set_keys(self, name: str, default: tuple[int, int, int] | None, keys: dict[str, tuple[int, int, int]]) -> dict:
        """Color LEDs by name; the rest keep their color, or take ``default`` when given.

        Names are matched without regard to case. Names the device does not have are
        returned as ``unknown`` rather than refused, so one pattern can serve keyboards
        with and without a keypad or media keys.
        """
        with self.lock:
            self._device(name)
            by_name = {led["key"].casefold(): led["id"] for led in self.layouts[name]}
            current = dict(self.key_colors.get(name) or {})
            if not current and name in self.colors:
                current = {led_id: self.colors[name] for led_id in by_name.values()}
            if default is not None:
                current = {led_id: default for led_id in by_name.values()}
            unknown = [key for key in keys if key.casefold() not in by_name]
            for key, rgb in keys.items():
                if key.casefold() in by_name:
                    current[by_name[key.casefold()]] = rgb
            self._paint_leds(name, current)
            self.key_colors[name] = current
            self.colors.pop(name, None)
            return {"ok": True, "painted": len(current), "unknown": unknown}

    def list(self) -> list[dict]:
        with self.lock:
            self._ready()
            return [{"device": name, "led_count": len(item[1])} for name, item in self.devices.items()]

    def set_color(self, name: str, rgb: tuple[int, int, int]) -> None:
        with self.lock:
            self._ready()
            if name not in self.devices:
                self._load_devices()  # plugged in after the bridge connected
            if name not in self.devices:
                raise LookupError(f"iCUE has no device named {name!r}")
            self._paint(name, rgb)
            self.colors[name] = rgb
            self.key_colors.pop(name, None)


class BridgeServer(ThreadingHTTPServer):
    # On Windows, address reuse lets a second bridge share the port, and two bridges fight over the lights.
    allow_reuse_address = False


def parse_rgb(body: bytes) -> tuple[int, int, int]:
    rgb = json.loads(body)["rgb"]
    if len(rgb) != 3 or not all(isinstance(value, int) and 0 <= value <= 255 for value in rgb):
        raise ValueError("rgb must be three integers from 0 to 255")
    return tuple(rgb)


def parse_keys(body: bytes) -> tuple[tuple[int, int, int] | None, dict[str, tuple[int, int, int]]]:
    payload = json.loads(body)
    keys = payload.get("keys") or {}
    if not isinstance(keys, dict) or not all(isinstance(key, str) and key for key in keys):
        raise ValueError("keys must map key names to [r, g, b]")
    default = payload.get("default")
    as_rgb = lambda value: parse_rgb(json.dumps({"rgb": value}).encode())
    return (as_rgb(default) if default is not None else None), {key: as_rgb(rgb) for key, rgb in keys.items()}


def make_handler(lights: ICueLights, token: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def reply(self, status: int, payload) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_body(self, limit: int = MAX_BODY_BYTES) -> bytes:
            size = int(self.headers.get("Content-Length") or 0)
            if size > limit:
                raise ValueError("Body too large")
            return self.rfile.read(size)

        def authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            return hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode())

        def guarded(self, action) -> None:
            if not self.authorized():
                self.close_connection = True
                return self.reply(401, {"error": "Unauthorized"})
            try:
                self.reply(200, action())
            except LookupError as error:
                self.reply(404, {"error": str(error)})
            except ICueUnavailable as error:
                self.reply(503, {"error": str(error)})
            except (ValueError, TypeError) as error:
                self.close_connection = True
                self.reply(400, {"error": str(error)})

        def do_GET(self) -> None:
            parts = self.path.split("/")
            if self.path == "/devices":
                self.guarded(lights.list)
            elif len(parts) == 4 and parts[1] == "devices" and parts[3] == "keys":
                self.guarded(lambda: lights.keys(unquote(parts[2])))
            else:
                self.reply(404, {"error": "Not found"})

        def do_PUT(self) -> None:
            parts = self.path.split("/")
            if len(parts) == 4 and parts[1] == "devices" and parts[3] == "color":
                name = unquote(parts[2])

                def apply() -> dict:
                    lights.set_color(name, parse_rgb(self.read_body()))
                    return {"ok": True}

                self.guarded(apply)
            elif len(parts) == 4 and parts[1] == "devices" and parts[3] == "keys":
                name = unquote(parts[2])
                self.guarded(lambda: lights.set_keys(name, *parse_keys(self.read_body(MAX_KEYS_BODY_BYTES))))
            else:
                self.close_connection = True
                self.reply(404, {"error": "Not found"})

        def log_message(self, *args) -> None:
            pass  # scheme frames would flood the log

    return Handler


def main() -> None:
    import cuesdk

    here = Path(__file__).resolve().parent
    logging.basicConfig(
        filename=here / "icue_bridge.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = BridgeConfig.load(here / "icue_bridge.json")
    token = (here / "icue_token.txt").read_text().strip()
    if len(token) < 32:
        raise SystemExit("icue_token.txt must hold a token of at least 32 characters")
    lights = ICueLights(cuesdk.CueSdk(), cuesdk, config.device_types)
    # Bind first: a bridge that is already running must not see a second iCUE session open.
    try:
        server = BridgeServer((config.bind, config.port), make_handler(lights, token))
    except OSError as error:
        log.error("Port %s is taken, is another bridge running? %s", config.port, error)
        raise SystemExit(1) from error
    lights.start()
    log.info("Listening on %s:%s for %s", config.bind, config.port, ", ".join(config.device_types))
    server.serve_forever()


if __name__ == "__main__":
    main()
