"""Run on any machine, no iCUE needed: python3 -m unittest discover -s bridge"""

import json
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from http.server import ThreadingHTTPServer
from pathlib import Path

from icue_bridge import BridgeConfig, BridgeServer, ICueLights, ICueUnavailable, led_name, make_handler, parse_keys, parse_rgb

TOKEN = "t" * 32


class Error(Enum):
    CE_Success = 0
    CE_NoControl = 2


class State(Enum):
    CSS_ConnectionLost = 5
    CSS_Connected = 6


@dataclass
class Color:
    id: int
    r: int
    g: int
    b: int
    a: int


FAKE_TYPES = types.SimpleNamespace(
    CorsairError=Error,
    CorsairSessionState=State,
    CorsairDeviceFilter=lambda device_type_mask: device_type_mask,
    CorsairDeviceType=types.SimpleNamespace(CDT_Keyboard=1, CDT_Mouse=2, CDT_Cooler=256),
    CorsairAccessLevel=types.SimpleNamespace(CAL_ExclusiveLightingControl=1),
    CorsairLedColor=Color,
)


class FakeSdk:
    def __init__(self):
        self.controlled, self.painted = [], {}
        self.result = Error.CE_Success
        self.models = {"K70": ("id-k", 3), "Harpoon": ("id-m", 2)}

    def connect(self, handler):
        self.handler = handler
        return Error.CE_Success

    def get_devices(self, wanted):
        self.wanted = wanted
        return [
            types.SimpleNamespace(device_id=device_id, model=model)
            for model, (device_id, _) in self.models.items()
        ], Error.CE_Success

    def get_led_positions(self, device_id):
        count = next(leds for known, leds in self.models.values() if known == device_id)
        return [types.SimpleNamespace(id=index + 100) for index in range(count)], Error.CE_Success

    def request_control(self, device_id, level):
        if (device_id, level) in self.controlled:
            return Error.CE_NoControl  # as real iCUE did for a repeat request
        self.controlled.append((device_id, level))
        return Error.CE_Success

    def set_led_colors(self, device_id, colors):
        self.painted[device_id] = colors
        return self.result


class LightsTests(unittest.TestCase):
    def setUp(self):
        self.sdk = FakeSdk()
        self.lights = ICueLights(self.sdk, FAKE_TYPES)
        self.lights.takeover_attempts, self.lights.takeover_delay_seconds = 3, 0
        self.lights.sync(True)

    def test_connecting_takes_exclusive_control_of_every_device(self):
        self.assertEqual(self.sdk.controlled, [("id-k", 1), ("id-m", 1)])

    def test_asks_only_for_keyboards_and_mice_by_default_so_openrgb_keeps_the_board(self):
        self.assertEqual(self.sdk.wanted, 3)

    def test_device_types_are_tunable(self):
        sdk = FakeSdk()
        ICueLights(sdk, FAKE_TYPES, ("keyboard", "cooler")).sync(True)
        self.assertEqual(sdk.wanted, 257)

    def test_lists_devices_with_led_counts(self):
        self.assertEqual(
            self.lights.list(),
            [{"device": "K70", "led_count": 3}, {"device": "Harpoon", "led_count": 2}],
        )

    def test_color_reaches_every_led_of_the_named_device(self):
        self.lights.set_color("K70", (1, 2, 3))
        self.assertEqual(
            self.sdk.painted["id-k"],
            [Color(100, 1, 2, 3, 255), Color(101, 1, 2, 3, 255), Color(102, 1, 2, 3, 255)],
        )
        self.assertNotIn("id-m", self.sdk.painted)

    def test_unknown_device_is_a_lookup_error(self):
        with self.assertRaises(LookupError):
            self.lights.set_color("Nope", (1, 2, 3))

    def test_unknown_device_leaves_the_known_ones_working(self):
        with self.assertRaises(LookupError):
            self.lights.set_color("Nope", (1, 2, 3))
        self.lights.set_color("K70", (1, 2, 3))
        self.assertEqual(self.sdk.painted["id-k"][0], Color(100, 1, 2, 3, 255))

    def test_failed_reload_keeps_the_known_devices(self):
        self.sdk.get_led_positions = lambda device_id: (None, Error.CE_NoControl)
        with self.assertRaises(ICueUnavailable):
            self.lights.set_color("Nope", (1, 2, 3))
        self.lights.set_color("K70", (1, 2, 3))
        self.assertEqual(self.sdk.painted["id-k"][0], Color(100, 1, 2, 3, 255))

    def test_reconnect_that_cannot_take_control_recovers_on_the_next_command(self):
        self.lights.sync(False)  # iCUE still holds control from before, so the request is refused
        self.lights.sync(True)
        self.assertEqual(self.lights.devices, {})
        self.sdk.controlled.clear()
        self.lights.set_color("K70", (1, 2, 3))
        self.assertEqual(self.sdk.painted["id-k"][0], Color(100, 1, 2, 3, 255))

    def test_devices_listed_late_after_reconnecting_still_get_the_last_color(self):
        self.lights.set_color("K70", (1, 2, 3))
        self.lights.sync(False)
        self.sdk.painted.clear()
        self.sdk.controlled.clear()
        listed = self.sdk.get_devices
        answers = [([], Error.CE_Success)]  # iCUE lists nothing at first, as after a screen saver
        self.sdk.get_devices = lambda wanted: answers.pop() if answers else listed(wanted)
        self.lights.sync(True)
        self.assertEqual(self.sdk.painted["id-k"][0], Color(100, 1, 2, 3, 255))
        self.assertIn(("id-k", 1), self.sdk.controlled)

    def test_disconnected_is_unavailable(self):
        self.lights.sync(False)
        with self.assertRaises(ICueUnavailable):
            self.lights.set_color("K70", (1, 2, 3))

    def test_refused_paint_is_unavailable_and_not_remembered(self):
        self.sdk.result = Error.CE_NoControl
        with self.assertRaises(ICueUnavailable):
            self.lights.set_color("K70", (1, 2, 3))
        self.assertEqual(self.lights.colors, {})

    def test_reconnecting_repaints_the_last_color(self):
        self.lights.set_color("K70", (1, 2, 3))
        self.lights.sync(False)
        self.sdk.painted.clear()
        self.sdk.controlled.clear()  # a restarted iCUE starts a new session
        self.lights.sync(True)
        self.assertEqual(self.sdk.painted["id-k"][0], Color(100, 1, 2, 3, 255))


class ConfigTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "icue_bridge.json"
            if text is not None:
                path.write_text(text)
            return BridgeConfig.load(path)

    def test_defaults_without_a_file(self):
        self.assertEqual(self.load(None), BridgeConfig("0.0.0.0", 6743, ("keyboard", "mouse")))

    def test_reads_settings(self):
        config = self.load('{"bind": "127.0.0.1", "port": 7000, "device_types": ["cooler"]}')
        self.assertEqual(config, BridgeConfig("127.0.0.1", 7000, ("cooler",)))

    def test_refuses_bad_settings(self):
        for text in ('{"device_types": ["toaster"]}', '{"device_types": []}', '{"port": 0}', '{"prot": 1}'):
            with self.assertRaises(ValueError, msg=text):
                self.load(text)


class ServerTests(unittest.TestCase):
    def test_a_second_bridge_cannot_share_the_port(self):
        handler = make_handler(ICueLights(FakeSdk(), FAKE_TYPES), TOKEN)
        first = BridgeServer(("127.0.0.1", 0), handler)
        self.addCleanup(first.server_close)
        with self.assertRaises(OSError):
            BridgeServer(first.server_address, handler)


class ParseRgbTests(unittest.TestCase):
    def test_accepts_three_bytes(self):
        self.assertEqual(parse_rgb(b'{"rgb": [0, 128, 255]}'), (0, 128, 255))

    def test_rejects_bad_values(self):
        for body in (b'{"rgb": [0, 0]}', b'{"rgb": [0, 0, 256]}', b'{"rgb": [0, 0, "1"]}'):
            with self.assertRaises(ValueError):
                parse_rgb(body)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.sdk = FakeSdk()
        lights = ICueLights(self.sdk, FAKE_TYPES)
        lights.sync(True)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lights, TOKEN))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None, token=TOKEN):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_wrong_token_is_refused_and_changes_nothing(self):
        status, _ = self.call("PUT", "/devices/K70/color", {"rgb": [1, 2, 3]}, token="x" * 32)
        self.assertEqual(status, 401)
        self.assertEqual(self.sdk.painted, {})

    def test_sets_a_color_by_url_encoded_name(self):
        self.sdk.models["K70 RGB PRO"] = ("id-p", 1)
        self.call("GET", "/devices")
        self.sdk.controlled.clear()
        status, _ = self.call("PUT", "/devices/K70%20RGB%20PRO/color", {"rgb": [9, 8, 7]})
        self.assertEqual(status, 200)
        self.assertEqual(self.sdk.painted["id-p"], [Color(100, 9, 8, 7, 255)])

    def test_unknown_device_is_404_and_bad_body_is_400(self):
        self.assertEqual(self.call("PUT", "/devices/Nope/color", {"rgb": [1, 2, 3]})[0], 404)
        self.assertEqual(self.call("PUT", "/devices/K70/color", {"rgb": [1]})[0], 400)


KEY_TYPES = types.SimpleNamespace(
    **vars(FAKE_TYPES),
    CorsairLedGroup=types.SimpleNamespace(_reverse_map_={0: "CLG_Keyboard", 4: "CLG_Mouse"}),
    CorsairLedId_Keyboard=types.SimpleNamespace(_reverse_map_={1: "CLK_Escape", 30: "CLK_W", 71: "CLK_Space"}),
)
MOUSE_LED = (4 << 16) | 1


class KeyboardSdk(FakeSdk):
    """A keyboard whose LEDs are Escape, W and Space, and a one-LED mouse, with positions."""

    def get_led_positions(self, device_id):
        if device_id == "id-k":
            return [types.SimpleNamespace(id=1, cx=10.0, cy=5.0), types.SimpleNamespace(id=30, cx=40.25, cy=45.0),
                    types.SimpleNamespace(id=71, cx=120.0, cy=100.0)], Error.CE_Success
        return [types.SimpleNamespace(id=MOUSE_LED, cx=0.0, cy=0.0)], Error.CE_Success


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.sdk = KeyboardSdk()
        self.lights = ICueLights(self.sdk, KEY_TYPES)
        self.lights.takeover_attempts, self.lights.takeover_delay_seconds = 3, 0
        self.lights.sync(True)

    def painted(self, device="id-k"):
        return {(color.id): (color.r, color.g, color.b) for color in self.sdk.painted[device]}

    def test_leds_are_named_after_their_keys_with_positions(self):
        self.assertEqual(self.lights.keys("K70"), [
            {"key": "Escape", "x": 10.0, "y": 5.0}, {"key": "W", "x": 40.2, "y": 45.0}, {"key": "Space", "x": 120.0, "y": 100.0},
        ])
        self.assertEqual(self.lights.keys("Harpoon"), [{"key": "Mouse 1", "x": 0.0, "y": 0.0}])
        self.assertEqual(led_name(FAKE_TYPES, 7), "0 7")  # an SDK without key names still names every LED

    def test_named_keys_take_their_colors_and_the_rest_the_default(self):
        result = self.lights.set_keys("K70", (0, 0, 9), {"w": (255, 0, 0), "Numpad5": (1, 1, 1)})
        self.assertEqual(self.painted(), {1: (0, 0, 9), 30: (255, 0, 0), 71: (0, 0, 9)})
        self.assertEqual(result["unknown"], ["Numpad5"])

    def test_keys_left_out_keep_their_color(self):
        self.lights.set_color("K70", (5, 5, 5))
        self.lights.set_keys("K70", None, {"Space": (9, 9, 9)})
        self.assertEqual(self.painted(), {1: (5, 5, 5), 30: (5, 5, 5), 71: (9, 9, 9)})
        self.lights.set_keys("K70", None, {"Escape": (1, 2, 3)})
        self.assertEqual(self.painted(), {1: (1, 2, 3), 30: (5, 5, 5), 71: (9, 9, 9)})

    def test_a_whole_device_color_replaces_a_pattern_and_reconnecting_repaints_the_pattern(self):
        self.lights.set_keys("K70", (0, 0, 0), {"W": (255, 0, 0)})
        self.lights.sync(False)
        self.sdk.painted.clear()
        self.sdk.controlled.clear()
        self.lights.sync(True)
        self.assertEqual(self.painted()[30], (255, 0, 0))
        self.lights.set_color("K70", (7, 7, 7))
        self.assertNotIn("K70", self.lights.key_colors)

    def test_key_bodies_are_checked(self):
        self.assertEqual(parse_keys(b'{"keys": {"W": [1, 2, 3]}}'), (None, {"W": (1, 2, 3)}))
        for bad in (b'{"keys": {"W": [1, 2]}}', b'{"keys": ["W"]}', b'{"default": [300, 0, 0]}'):
            with self.subTest(bad), self.assertRaises(ValueError):
                parse_keys(bad)


class KeyServerTests(unittest.TestCase):
    def setUp(self):
        self.sdk = KeyboardSdk()
        lights = ICueLights(self.sdk, KEY_TYPES)
        lights.takeover_attempts, lights.takeover_delay_seconds = 3, 0
        lights.sync(True)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lights, TOKEN))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None):
        request = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Authorization": f"Bearer {TOKEN}"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_keys_are_listed_and_painted_over_http(self):
        self.assertEqual(self.call("GET", "/devices/K70/keys")[1]["key"], "W")
        keys = {f"Key{n}": [n % 256, 0, 0] for n in range(200)}  # far over the plain color body limit
        answer = self.call("PUT", "/devices/K70/keys", {"default": [0, 0, 0], "keys": {**keys, "W": [0, 255, 0]}})
        self.assertEqual((answer["painted"], len(answer["unknown"])), (3, 200))
        self.assertEqual(self.sdk.painted["id-k"][1], Color(30, 0, 255, 0, 255))


if __name__ == "__main__":
    unittest.main()
