import asyncio
import json
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.core.config import AppConfig
from app.core.models import LightCreate
from app.integrations.icue import ICueAdapter, ICueAddress
from app.integrations.router import LightRouter, light_address
from app.services.application import LightService

TOKEN = "t" * 32
KEYBOARD = "K70 RGB PRO"


class FakeBridge:
    """Answers like bridge/icue_bridge.py and records the colors it was sent."""

    def __init__(self):
        self.colors, self.auth, self.unavailable = [], [], False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def reply(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                outer.auth.append(self.headers["Authorization"])
                self.reply(200, [{"device": KEYBOARD, "led_count": 123}])

            def do_PUT(self):
                outer.auth.append(self.headers["Authorization"])
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if outer.unavailable:
                    return self.reply(503, {"error": "iCUE is not connected"})
                if self.path != "/devices/K70%20RGB%20PRO/color":
                    return self.reply(404, {"error": "iCUE has no device named that"})
                outer.colors.append(tuple(body["rgb"]))
                self.reply(200, {"ok": True})

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class ICueAdapterTests(unittest.TestCase):
    def setUp(self):
        self.bridge = FakeBridge()
        self.addCleanup(self.bridge.close)
        self.adapter = ICueAdapter(TOKEN, timeout=2)
        self.keyboard = str(ICueAddress("127.0.0.1", KEYBOARD, self.bridge.port))

    def test_address_round_trip(self):
        address = ICueAddress.parse("icue://192.168.1.20:6743/K70 RGB PRO")
        self.assertEqual(address, ICueAddress("192.168.1.20", KEYBOARD))
        self.assertEqual(str(address), "icue://192.168.1.20:6743/K70 RGB PRO")

    def test_color_is_sent_with_the_token(self):
        asyncio.run(self.adapter.apply(self.keyboard, color="#FF8000"))
        self.assertEqual(self.bridge.colors, [(255, 128, 0)])
        self.assertEqual(self.bridge.auth, [f"Bearer {TOKEN}"])

    def test_brightness_scales_the_remembered_color_and_off_is_black(self):
        asyncio.run(self.adapter.apply(self.keyboard, color="#C86432"))
        asyncio.run(self.adapter.apply(self.keyboard, brightness=50))
        asyncio.run(self.adapter.apply(self.keyboard, on=False))
        asyncio.run(self.adapter.apply(self.keyboard, on=True))
        self.assertEqual(
            self.bridge.colors, [(200, 100, 50), (100, 50, 25), (0, 0, 0), (100, 50, 25)]
        )

    def test_unknown_device_is_a_lookup_error(self):
        missing = str(ICueAddress("127.0.0.1", "Nope", self.bridge.port))
        with self.assertRaises(LookupError):
            asyncio.run(self.adapter.apply(missing, color="#FFFFFF"))
        with self.assertRaises(LookupError):
            asyncio.run(self.adapter.status(missing))

    def test_icue_being_down_is_a_connection_error(self):
        self.bridge.unavailable = True
        with self.assertRaisesRegex(ConnectionError, "not connected"):
            asyncio.run(self.adapter.apply(self.keyboard, color="#FFFFFF"))

    def test_bridge_being_down_is_a_connection_error(self):
        self.bridge.close()
        self.addCleanup(lambda: setattr(self.bridge, "close", lambda: None))
        self.bridge.close = lambda: None
        with self.assertRaisesRegex(ConnectionError, "unreachable"):
            asyncio.run(self.adapter.apply(self.keyboard, color="#FFFFFF"))

    def test_no_token_is_a_connection_error_without_calling_the_bridge(self):
        with self.assertRaisesRegex(ConnectionError, "LUNALUMIA_ICUE_TOKENS"):
            asyncio.run(ICueAdapter().apply(self.keyboard, color="#FFFFFF"))
        self.assertEqual(self.bridge.auth, [])

    def test_a_pc_with_its_own_token_uses_it(self):
        adapter = ICueAdapter(TOKEN, timeout=2, host_tokens={"127.0.0.1": "own" * 11})
        asyncio.run(adapter.apply(self.keyboard, color="#FFFFFF"))
        self.assertEqual(self.bridge.auth, ["Bearer " + "own" * 11])

    def test_host_tokens_setting(self):
        self.assertEqual(AppConfig.parse_host_tokens(""), {})
        self.assertEqual(
            AppConfig.parse_host_tokens("192.168.1.15=abc, 192.168.1.20=def"),
            {"192.168.1.15": "abc", "192.168.1.20": "def"},
        )
        with self.assertRaises(RuntimeError):
            AppConfig.parse_host_tokens("192.168.1.15")

    def test_status_confirms_the_device(self):
        self.assertEqual(asyncio.run(self.adapter.status(self.keyboard)), {"mac_address": None})

    def test_discovery_flags_lights_already_added(self):
        class Lights:
            def list(self):
                return [{"protocol": "icue", "ip_address": "127.0.0.1", "device": KEYBOARD}]

        service = LightService(Lights(), None, None, None, self.adapter)
        found = asyncio.run(service.discover_icue("127.0.0.1", self.bridge.port))
        self.assertEqual(found[0]["led_count"], 123)
        self.assertTrue(found[0]["configured"])
        self.assertEqual(found[0]["suggested_name"], KEYBOARD)


class PcDiscoveryTests(unittest.TestCase):
    def service(self, openrgb, icue):
        class Lights:
            def list(self):
                return []

        return LightService(Lights(), None, None, openrgb, icue)

    def controller(self, name, led_count):
        return types.SimpleNamespace(name=name, led_count=led_count)

    def openrgb(self, *controllers):
        async def devices(host, port):
            return list(controllers)

        return types.SimpleNamespace(devices=devices)

    def icue(self, *names):
        async def devices(host, port):
            return [{"device": name, "led_count": 5} for name in names]

        return types.SimpleNamespace(devices=devices)

    def down(self, error):
        async def devices(host, port):
            raise error

        return types.SimpleNamespace(devices=devices)

    def test_lists_both_sources_with_their_ports(self):
        service = self.service(self.openrgb(self.controller("ASUS Board", 3)), self.icue("K70 RGB PRO"))
        result = asyncio.run(service.discover_pc("192.168.1.15", 7000, 7001))
        self.assertEqual(
            [(d["protocol"], d["device"], d["port"]) for d in result["devices"]],
            [("openrgb", "ASUS Board", 7000), ("icue", "K70 RGB PRO", 7001)],
        )
        self.assertEqual(result["warnings"], [])
        self.assertTrue(result["openrgb"]["available"] and result["icue"]["available"])

    def test_warns_of_a_device_both_programs_offer(self):
        service = self.service(
            self.openrgb(self.controller("Corsair K70 RGB PRO V2", 115)), self.icue("K70 RGB PRO")
        )
        result = asyncio.run(service.discover_pc("192.168.1.15"))
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("look like one device", result["warnings"][0])

    def test_warns_of_a_device_with_no_leds(self):
        service = self.service(self.openrgb(self.controller("ASUS Board", 0)), self.icue())
        result = asyncio.run(service.discover_pc("192.168.1.15"))
        self.assertIn("no LEDs", result["warnings"][0])

    def test_one_source_being_down_still_lists_the_other(self):
        service = self.service(self.down(ConnectionRefusedError("refused")), self.icue("K70 RGB PRO"))
        result = asyncio.run(service.discover_pc("192.168.1.15"))
        self.assertEqual(result["openrgb"], {"available": False, "error": "refused"})
        self.assertEqual([d["device"] for d in result["devices"]], ["K70 RGB PRO"])

    def test_refuses_an_invalid_address(self):
        with self.assertRaises(ValueError):
            asyncio.run(self.service(None, None).discover_pc("not-an-ip"))


class RoutingTests(unittest.TestCase):
    def test_router_sends_each_protocol_to_its_adapter(self):
        calls = []

        def recorder(kind):
            class Adapter:
                async def apply(self, address, **state):
                    calls.append(kind)

            return Adapter()

        router = LightRouter(recorder("wiz"), recorder("openrgb"), recorder("icue"))
        for address in ("192.168.1.8", "openrgb://192.168.1.15:6742/Board", "icue://192.168.1.15:6743/K70"):
            asyncio.run(router.apply(address, color="#FFFFFF"))
        self.assertEqual(calls, ["wiz", "openrgb", "icue"])

    def test_light_address_for_icue(self):
        light = {"ip_address": "192.168.1.15", "protocol": "icue", "device": "K70"}
        self.assertEqual(light_address(light), "icue://192.168.1.15:6743/K70")
        self.assertEqual(light_address({**light, "port": 7001}), "icue://192.168.1.15:7001/K70")

    def test_light_create_requires_a_device_for_icue(self):
        LightCreate(name="Keyboard", ip_address="192.168.1.15", protocol="icue", device="K70")
        with self.assertRaises(ValueError):
            LightCreate(name="Keyboard", ip_address="192.168.1.15", protocol="icue")
        with self.assertRaises(ValueError):
            LightCreate(name="Bulb", ip_address="192.168.1.8", port=7000)


if __name__ == "__main__":
    unittest.main()
