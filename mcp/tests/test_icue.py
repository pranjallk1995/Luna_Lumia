import asyncio
import json
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.core import tenancy
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


class MovedPcTests(unittest.TestCase):
    """A PC that got a new IP is found by the devices it offers."""

    def setUp(self):
        owner = tenancy.acting_as(tenancy.OWNER)
        owner.__enter__()
        self.addCleanup(owner.__exit__, None, None, None)

    def rows(self):
        return [
            {"id": 1, "name": "PC Keyboard", "ip_address": "192.168.1.15", "protocol": "icue", "device": "K70 RGB PRO", "port": None},
            {"id": 2, "name": "PC Case", "ip_address": "192.168.1.15", "protocol": "openrgb", "device": "ASUS Board", "port": None},
            {"id": 3, "name": "Bulb", "ip_address": "192.168.1.8", "protocol": "wiz", "device": None, "port": None},
        ]

    def service(self, rows, offers):
        """``offers`` maps (host, port) to the device names a PC offers there."""

        class Lights:
            def __init__(self):
                self.rows = rows
            def list(self):
                return [dict(row) for row in self.rows]
            def relocate(self, new_ips):
                for row in self.rows:
                    row["ip_address"] = new_ips.get(row["id"], row["ip_address"])

        async def openrgb_devices(host, port):
            return [types.SimpleNamespace(name=name, led_count=1) for name in offers[(host, port)]]

        async def icue_devices(host, port):
            return [{"device": name, "led_count": 1} for name in offers[(host, port)]]

        service = LightService(
            Lights(), None, None,
            types.SimpleNamespace(devices=openrgb_devices), types.SimpleNamespace(devices=icue_devices),
        )

        async def listening(host, port):
            return (host, port) in offers

        service._listening = listening
        return service

    def test_follows_the_pc_to_its_new_ip(self):
        rows = self.rows()
        offers = {("192.168.1.11", 6743): {"K70 RGB PRO"}, ("192.168.1.11", 6742): {"ASUS Board"}}
        result = asyncio.run(self.service(rows, offers).find_moved_pc_lights())
        self.assertEqual(result["scanned"], ["192.168.1.0/24"])
        self.assertEqual({m["name"]: (m["from"], m["to"]) for m in result["moved"]}, {
            "PC Keyboard": ("192.168.1.15", "192.168.1.11"), "PC Case": ("192.168.1.15", "192.168.1.11"),
        })
        self.assertEqual([row["ip_address"] for row in rows], ["192.168.1.11", "192.168.1.11", "192.168.1.8"])

    def test_a_light_still_answering_stays(self):
        rows = self.rows()
        offers = {("192.168.1.15", 6743): {"K70 RGB PRO"}, ("192.168.1.15", 6742): {"ASUS Board"}}
        result = asyncio.run(self.service(rows, offers).find_moved_pc_lights())
        self.assertEqual((result["moved"], sorted(result["unchanged"])), ([], ["PC Case", "PC Keyboard"]))

    def test_two_pcs_with_the_device_is_ambiguous_and_none_is_not_found(self):
        rows = self.rows()
        offers = {("192.168.1.11", 6743): {"K70 RGB PRO"}, ("192.168.1.12", 6743): {"K70 RGB PRO"}}
        result = asyncio.run(self.service(rows, offers).find_moved_pc_lights())
        self.assertEqual(result["ambiguous"], [{"name": "PC Keyboard", "hosts": ["192.168.1.11", "192.168.1.12"]}])
        self.assertEqual(result["not_found"], ["PC Case"])
        self.assertEqual(rows[0]["ip_address"], "192.168.1.15")

    def test_a_pc_that_does_not_answer_its_devices_is_skipped(self):
        rows = self.rows()

        async def refused(host, port):
            raise ConnectionRefusedError("refused")

        service = self.service(rows, {("192.168.1.11", 6743): set()})
        service.icue = types.SimpleNamespace(devices=refused)
        result = asyncio.run(service.find_moved_pc_lights())
        self.assertEqual((result["moved"], sorted(result["not_found"])), ([], ["PC Case", "PC Keyboard"]))

    def test_does_not_take_an_address_another_light_holds(self):
        rows = self.rows() + [
            {"id": 4, "name": "Other K70", "ip_address": "192.168.1.11", "protocol": "icue", "device": "K70 RGB PRO", "port": None},
        ]
        result = asyncio.run(self.service(rows, {("192.168.1.11", 6743): {"K70 RGB PRO"}}).find_moved_pc_lights())
        self.assertEqual(result["blocked"], ["PC Keyboard"])
        self.assertEqual(rows[0]["ip_address"], "192.168.1.15")

    def test_scans_the_given_subnet(self):
        offers = {("10.0.0.5", 6743): {"K70 RGB PRO"}, ("10.0.0.5", 6742): {"ASUS Board"}}
        result = asyncio.run(self.service(self.rows(), offers).find_moved_pc_lights("10.0.0"))
        self.assertEqual((result["scanned"], len(result["moved"])), (["10.0.0.0/24"], 2))
        with self.assertRaises(ValueError):
            asyncio.run(self.service(self.rows(), {}).find_moved_pc_lights("not.a.net"))

    def test_move_pc_lights_moves_every_light_of_that_pc(self):
        rows = self.rows()
        moved = self.service(rows, {}).move_pc_lights("192.168.1.15", "192.168.1.11")
        self.assertEqual(sorted(light["name"] for light in moved), ["PC Case", "PC Keyboard"])
        self.assertEqual(rows[2]["ip_address"], "192.168.1.8")

    def test_move_pc_lights_refuses_a_clash_without_moving_anything(self):
        rows = self.rows() + [
            {"id": 4, "name": "Other K70", "ip_address": "192.168.1.11", "protocol": "icue", "device": "K70 RGB PRO", "port": None},
        ]
        with self.assertRaises(ValueError):
            self.service(rows, {}).move_pc_lights("192.168.1.15", "192.168.1.11")
        self.assertEqual([row["ip_address"] for row in rows[:2]], ["192.168.1.15", "192.168.1.15"])

    def test_refresh_rescans_for_a_silent_pc_light(self):
        from app.services.application import LumiaService

        class Control:
            polls = 0
            async def poll_statuses(self):
                Control.polls += 1
                return [{"light": {"id": 1, "protocol": "icue", "mac_address": None}, "ok": Control.polls > 1}]

        class Lights:
            rescanned = False
            async def discover(self, space): raise AssertionError("no bulb scan expected")
            async def find_moved_pc_lights(self): Lights.rescanned = True

        result = asyncio.run(LumiaService(Lights(), None, None, Control(), None, None, None, None, None).refresh_lights())
        self.assertEqual((Lights.rescanned, Control.polls, result[0]["ok"]), (True, 2, True))


class RescanCooldownTests(unittest.TestCase):
    """A light that stays silent after a scan does not trigger another for a while."""

    def setUp(self):
        owner = tenancy.acting_as(tenancy.OWNER)
        owner.__enter__()
        self.addCleanup(owner.__exit__, None, None, None)

    def service(self, recovers):
        from app.services.application import LumiaService

        class Control:
            async def poll_statuses(self):
                return [{"light": {"id": 1, "protocol": "icue", "mac_address": None}, "ok": lights.scans > 0 and recovers}]

        class Lights:
            scans = 0
            async def find_moved_pc_lights(self):
                self.scans += 1

        lights = Lights()
        return LumiaService(lights, None, None, Control(), None, None, None, None, None), lights

    def refresh(self, service):
        return asyncio.run(service.refresh_lights())

    def test_a_pc_still_silent_after_a_scan_is_not_scanned_for_again_soon(self):
        service, lights = self.service(recovers=False)
        self.refresh(service)
        self.refresh(service)
        self.assertEqual(lights.scans, 1)

    def test_scanning_resumes_after_the_cooldown(self):
        service, lights = self.service(recovers=False)
        self.refresh(service)
        service.quiet_until["pcs"] = 0.0
        self.refresh(service)
        self.assertEqual(lights.scans, 2)

    def test_a_scan_that_found_the_pc_sets_no_cooldown(self):
        service, lights = self.service(recovers=True)
        self.refresh(service)
        self.assertEqual(service.quiet_until["pcs"], 0.0)


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
