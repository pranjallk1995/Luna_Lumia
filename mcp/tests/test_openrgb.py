import asyncio
import socket
import struct
import threading
import time
import unittest

from app.core.models import LightCreate
from app.integrations.openrgb import (
    HEADER,
    MAGIC,
    REQUEST_CONTROLLER_COUNT,
    REQUEST_CONTROLLER_DATA,
    SET_CUSTOM_MODE,
    UPDATE_LEDS,
    ControllerParser,
    OpenRGBAdapter,
    OpenRGBAddress,
)
from app.integrations.router import LightRouter, light_address


def text(value: str) -> bytes:
    raw = value.encode() + b"\x00"
    return struct.pack("<H", len(raw)) + raw


def controller_blob(name: str, leds: int, first=(10, 20, 30), matrix=False, zones=None) -> bytes:
    """A protocol-0 controller description, as OpenRGB sends it; ``zones`` lists (name, LED count)."""
    zones = zones or [("Keys", leds)]
    body = struct.pack("<i", 5) + text(name) + text("desc") + text("1.0") + text("SN") + text("HID")
    body += struct.pack("<H", 1) + struct.pack("<i", 0)  # one mode, active mode 0
    body += text("Direct") + struct.pack("<iIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0)
    body += struct.pack("<H", 1) + bytes((1, 2, 3, 0))  # one mode color
    body += struct.pack("<H", len(zones))
    for zone_name, zone_leds in zones:
        body += text(zone_name) + struct.pack("<iIII", 2, zone_leds, zone_leds, zone_leds)
        if matrix:
            grid = struct.pack("<II", 1, 2) + struct.pack("<II", 0, 1)
            body += struct.pack("<H", len(grid)) + grid
        else:
            body += struct.pack("<H", 0)
    body += struct.pack("<H", leds) + b"".join(text(f"Key {i}") + struct.pack("<I", i) for i in range(leds))
    body += struct.pack("<H", leds) + bytes((*first, 0)) * leds
    return struct.pack("<I", len(body) + 4) + body


class FakeOpenRGBServer:
    """Answers controller queries and records LED updates, like OpenRGB's SDK server."""

    def __init__(self, devices: list[tuple[str, int]]) -> None:
        self.devices = devices
        self.packets: list[tuple[int, int, bytes]] = []
        self.sessions: list[socket.socket] = []
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def reply(self, conn, device, packet_id, payload):
        conn.sendall(HEADER.pack(MAGIC, device, packet_id, len(payload)) + payload)

    def serve(self):
        while True:
            conn, _ = self.listener.accept()
            self.sessions.append(conn)
            threading.Thread(target=self.session, args=(conn,), daemon=True).start()

    def drop_sessions(self):
        """End every session from the server side, as restarting OpenRGB does."""
        for conn in self.sessions:
            conn.shutdown(socket.SHUT_RDWR)
        self.sessions.clear()

    def session(self, conn):
        with conn:
            while True:
                header = conn.recv(HEADER.size, socket.MSG_WAITALL)
                if len(header) < HEADER.size:
                    return
                _, device, packet_id, size = HEADER.unpack(header)
                payload = conn.recv(size, socket.MSG_WAITALL) if size else b""
                self.packets.append((packet_id, device, payload))
                if packet_id == REQUEST_CONTROLLER_COUNT:
                    # An unsolicited notification first, which the client must skip.
                    self.reply(conn, 0, 100, b"")
                    self.reply(conn, 0, packet_id, struct.pack("<I", len(self.devices)))
                elif packet_id == REQUEST_CONTROLLER_DATA:
                    name, leds, *zones = self.devices[device]
                    self.reply(conn, device, packet_id, controller_blob(name, leds, zones=zones[0] if zones else None))

    def updates(self, at_least: int = 1):
        """LED updates received so far, waiting briefly: the client does not wait for them."""
        deadline = time.monotonic() + 2
        while True:
            found = [(d, p) for packet_id, d, p in list(self.packets) if packet_id == UPDATE_LEDS]
            if len(found) >= at_least or time.monotonic() > deadline:
                return found
            time.sleep(0.01)

    def close(self):
        self.listener.close()


class OpenRGBTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeOpenRGBServer([("ASUS B860M MAX GAMING AX", 3), ("Corsair K70 RGB PRO V2", 4)])
        self.adapter = OpenRGBAdapter(timeout=2)
        self.keyboard = str(OpenRGBAddress("127.0.0.1", "Corsair K70 RGB PRO V2", self.server.port))

    def tearDown(self):
        self.server.close()

    def colors(self, payload):
        size, count = struct.unpack_from("<IH", payload)
        self.assertEqual(size, len(payload))
        return [tuple(payload[6 + i * 4 : 9 + i * 4]) for i in range(count)]

    def test_address_round_trip(self):
        address = OpenRGBAddress.parse("openrgb://192.168.1.20:6742/Corsair K70 RGB PRO V2")
        self.assertEqual(address, OpenRGBAddress("192.168.1.20", "Corsair K70 RGB PRO V2"))
        self.assertEqual(str(address), "openrgb://192.168.1.20:6742/Corsair K70 RGB PRO V2")

    def test_parser_reads_name_leds_and_first_color(self):
        for matrix in (False, True):
            controller = ControllerParser(controller_blob("Mouse", 2, (9, 8, 7), matrix)).parse(4)
            self.assertEqual((controller.index, controller.name, controller.led_count), (4, "Mouse", 2))
            self.assertEqual(controller.first_color, (9, 8, 7))

    def test_color_fills_every_led_of_the_named_device_in_direct_mode(self):
        asyncio.run(self.adapter.apply(self.keyboard, color="#FF8000"))
        self.server.updates()
        self.assertIn((SET_CUSTOM_MODE, 1, b""), self.server.packets)
        device, payload = self.server.updates()[-1]
        self.assertEqual(device, 1)
        self.assertEqual(self.colors(payload), [(255, 128, 0)] * 4)

    def test_direct_mode_is_set_once_per_connection(self):
        for color in ("#FF0000", "#00FF00", "#0000FF"):
            asyncio.run(self.adapter.apply(self.keyboard, color=color))
        self.server.updates(3)
        self.assertEqual(sum(1 for p in self.server.packets if p[0] == SET_CUSTOM_MODE), 1)

    def test_brightness_scales_the_remembered_color_and_off_is_black(self):
        asyncio.run(self.adapter.apply(self.keyboard, color="#C86432"))
        asyncio.run(self.adapter.apply(self.keyboard, brightness=50))
        self.assertEqual(self.colors(self.server.updates(2)[-1][1])[0], (100, 50, 25))
        asyncio.run(self.adapter.apply(self.keyboard, on=False))
        self.assertEqual(self.colors(self.server.updates(3)[-1][1])[0], (0, 0, 0))
        asyncio.run(self.adapter.apply(self.keyboard, on=True))
        self.assertEqual(self.colors(self.server.updates(4)[-1][1])[0], (100, 50, 25))

    def test_color_temperature_becomes_white(self):
        asyncio.run(self.adapter.apply(self.keyboard, color_temp=6500))
        red, green, blue = self.colors(self.server.updates()[-1][1])[0]
        self.assertTrue(red > 240 and green > 240 and blue > 240)

    def test_unknown_device_is_an_error(self):
        missing = str(OpenRGBAddress("127.0.0.1", "Nope", self.server.port))
        with self.assertRaises(LookupError):
            asyncio.run(self.adapter.apply(missing, color="#FFFFFF"))

    def test_devices_and_status(self):
        devices = asyncio.run(self.adapter.devices("127.0.0.1", self.server.port))
        self.assertEqual(
            [(device.name, device.led_count) for device in devices],
            [("ASUS B860M MAX GAMING AX", 3), ("Corsair K70 RGB PRO V2", 4)],
        )
        self.assertEqual(asyncio.run(self.adapter.status(self.keyboard)), {"mac_address": None})

    def test_device_without_leds_is_an_error(self):
        self.server.devices[0] = ("ASUS B860M MAX GAMING AX", 0)
        board = str(OpenRGBAddress("127.0.0.1", "ASUS B860M MAX GAMING AX", self.server.port))
        with self.assertRaisesRegex(LookupError, "no LEDs"):
            asyncio.run(self.adapter.apply(board, color="#FFFFFF"))

    def test_device_resized_in_openrgb_gets_the_new_led_count(self):
        asyncio.run(self.adapter.apply(self.keyboard, color="#FF0000"))
        self.server.devices[1] = ("Corsair K70 RGB PRO V2", 6)
        asyncio.run(self.adapter.apply(self.keyboard, color="#00FF00"))
        self.assertEqual(self.colors(self.server.updates(2)[-1][1]), [(0, 255, 0)] * 6)

    def test_color_sent_after_the_server_restarted_still_arrives(self):
        asyncio.run(self.adapter.apply(self.keyboard, color="#FF0000"))
        self.server.drop_sessions()
        asyncio.run(self.adapter.apply(self.keyboard, color="#00FF00"))
        self.assertEqual(self.colors(self.server.updates(2)[-1][1])[0], (0, 255, 0))
        self.assertEqual(sum(1 for p in self.server.packets if p[0] == SET_CUSTOM_MODE), 2)

    def test_reconnects_after_the_server_drops_the_session(self):
        asyncio.run(self.adapter.apply(self.keyboard, color="#FF0000"))
        for connection in self.adapter.connections.values():
            connection.sock.close()
        asyncio.run(self.adapter.apply(self.keyboard, color="#00FF00"))
        self.assertEqual(self.colors(self.server.updates(2)[-1][1])[0], (0, 255, 0))

    def test_router_sends_openrgb_and_wiz_lights_to_their_adapter(self):
        calls = []

        class Wiz:
            async def apply(self, address, **state): calls.append(("wiz", address))

        class Fake(OpenRGBAdapter):
            async def apply(self, address, **state): calls.append(("openrgb", address))

        router = LightRouter(Wiz(), Fake())
        asyncio.run(router.apply("192.168.1.8", color="#FFFFFF"))
        asyncio.run(router.apply(self.keyboard, color="#FFFFFF"))
        self.assertEqual([kind for kind, _ in calls], ["wiz", "openrgb"])

    def test_light_address_by_protocol(self):
        self.assertEqual(light_address({"ip_address": "192.168.1.8", "protocol": "wiz"}), "192.168.1.8")
        self.assertEqual(
            light_address({"ip_address": "192.168.1.20", "protocol": "openrgb", "device": "Harpoon"}),
            "openrgb://192.168.1.20:6742/Harpoon",
        )
        self.assertEqual(
            light_address({"ip_address": "192.168.1.20", "protocol": "openrgb", "device": "Harpoon", "port": 7000}),
            "openrgb://192.168.1.20:7000/Harpoon",
        )

    def test_light_create_requires_device_for_openrgb_only(self):
        LightCreate(name="Keyboard", ip_address="192.168.1.20", protocol="openrgb", device="K70")
        with self.assertRaises(ValueError):
            LightCreate(name="Keyboard", ip_address="192.168.1.20", protocol="openrgb")
        with self.assertRaises(ValueError):
            LightCreate(name="Bulb", ip_address="192.168.1.8", device="K70")


BOARD = "ASUS B860M MAX GAMING AX"
HEADERS = [("Addressable RGB Header 1", 2), ("Addressable RGB Header 2", 2), ("Addressable RGB Header 3", 10)]


class PartTests(unittest.TestCase):
    """Lights that are parts of one board: a header, or LEDs of a chain on it."""

    def setUp(self):
        self.server = FakeOpenRGBServer([(BOARD, 14, HEADERS)])
        self.adapter = OpenRGBAdapter(timeout=2)

    def tearDown(self):
        self.server.close()

    def address(self, zone=None, leds=None):
        return str(OpenRGBAddress("127.0.0.1", BOARD, self.server.port, zone, leds))

    def last_colors(self):
        _, payload = self.server.updates()[-1]
        size, count = struct.unpack_from("<IH", payload)
        return [tuple(payload[6 + i * 4 : 9 + i * 4]) for i in range(count)]

    def test_the_parser_reads_zones_and_every_color(self):
        controller = ControllerParser(controller_blob(BOARD, 14, (1, 2, 3), zones=HEADERS)).parse(0)
        self.assertEqual(controller.zones, HEADERS)
        self.assertEqual(controller.colors, [(1, 2, 3)] * 14)
        self.assertEqual(controller.part("3", "2-4"), [5, 6, 7])
        self.assertEqual(controller.part("addressable rgb header 2", None), [2, 3])
        for zone, leds in (("4", None), ("3", "9-11"), ("3", "5-2")):
            with self.subTest(zone=zone, leds=leds), self.assertRaises((LookupError, ValueError)):
                controller.part(zone, leds)

    def test_a_part_keeps_its_place_in_the_address(self):
        address = OpenRGBAddress.parse(self.address("3", "2-25"))
        self.assertEqual((address.device, address.zone, address.leds), (BOARD, "3", "2-25"))
        self.assertEqual(light_address({"protocol": "openrgb", "ip_address": "10.0.0.2", "device": BOARD, "zone": "3", "leds": "26-33"}),
                         f"openrgb://10.0.0.2:6742/{BOARD}#zone=3&leds=26-33")

    def test_painting_one_part_leaves_the_others_as_they_were(self):
        asyncio.run(self.adapter.apply(self.address(), color="#000000"))
        asyncio.run(self.adapter.apply(self.address("3", "1"), color="#FF0000"))
        asyncio.run(self.adapter.apply(self.address("3", "2-4"), color="#0000FF"))
        colors = self.last_colors()
        self.assertEqual(colors[4], (255, 0, 0))
        self.assertEqual(colors[5:8], [(0, 0, 255)] * 3)
        self.assertEqual(colors[:4] + colors[8:], [(0, 0, 0)] * 10)

    def test_single_leds_of_a_part_take_their_own_colors(self):
        asyncio.run(self.adapter.apply(self.address("3", "6-10"), brightness=50, color="#000000",
                                       keys={"LED 1": "#FF0000", "led 5": "#00FF00", "W": "#FFFFFF"}))
        colors = self.last_colors()
        self.assertEqual(colors[9:14], [(128, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 128, 0)])
        self.assertEqual(len(asyncio.run(self.adapter.leds(self.address("3", "6-10")))), 5)
        self.assertEqual(asyncio.run(self.adapter.leds(self.address("1")))[-1], {"key": "LED 2", "x": 2, "y": 0})

    def test_a_part_can_be_a_light(self):
        LightCreate(name="Front banner", ip_address="10.0.0.2", protocol="openrgb", device=BOARD, zone="3", leds="2-25")
        for bad in ({"protocol": "icue", "device": "K70", "zone": "1"}, {"protocol": "openrgb", "device": BOARD, "leds": "25-2"},
                    {"protocol": "openrgb", "device": BOARD, "leds": "a-b"}):
            with self.subTest(bad), self.assertRaises(ValueError):
                LightCreate(name="Part", ip_address="10.0.0.2", **bad)


if __name__ == "__main__":
    unittest.main()
