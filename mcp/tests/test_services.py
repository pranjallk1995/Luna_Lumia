import asyncio
import json
import unittest

from pydantic import ValidationError

from app.core.errors import NotFoundError
from app.transport.http_routes import LumiaHTTPRoutes
from app.core.models import GroupCreate, LightState
from app.services.application import (
    BackgroundImageService,
    CollectionService,
    LightService,
    SceneService,
)

VISIA = "https://visia.example/api/public/images/"


class FakeCollections:
    def __init__(self, conflicts=()):
        self.conflicts = list(conflicts)
        self.collections = {
            7: {"id": 7, "kind": "room", "name": "Kitchen", "light_ids": [1],
                "light_names": ["Ceiling"], "light_image_urls": [], "background_image_url": None},
        }
        self.added = []

    def room_conflicts(self, light_ids): return self.conflicts
    def get(self, collection_id, kind=None):
        item = self.collections.get(collection_id)
        return item if item and kind in (None, item["kind"]) else None
    def list(self, kind=None): return list(self.collections.values())
    def add(self, entry, kind):
        self.added.append((entry.name, kind))
        self.collections[8] = {"id": 8, "kind": kind, "name": entry.name, "light_ids": entry.light_ids,
                               "light_names": [], "light_image_urls": [], "background_image_url": None}
        return 8
    def update_image(self, collection_id, url):
        return {**self.collections[collection_id], "background_image_url": url}


class FakeRoomImages:
    def list(self):
        return [
            {"room_key": "kitchen", "image_url": VISIA + "k"},
            {"room_key": "living_room", "image_url": VISIA + "l"},
        ]


class FakeLights:
    def __init__(self, rows=None):
        self.rows = rows or [{"id": 1, "name": "A", "ip_address": "192.168.1.8", "mac_address": None}]
        self.macs = []
    def list(self): return [dict(row) for row in self.rows]
    def get(self, light_id): return None
    def store_mac_address(self, light_id, mac): self.macs.append((light_id, mac))
    def relocate(self, new_ips):
        for row in self.rows:
            row["ip_address"] = new_ips.get(row["id"], row["ip_address"])


class FakeDiscovery:
    async def scan(self, broadcast_space):
        return [
            {"ip_address": "192.168.1.20", "mac_address": None, "protocol": "wiz"},
            {"ip_address": "192.168.1.8", "mac_address": "aabbccddeeff", "protocol": "wiz"},
        ]


class CollectionServiceTests(unittest.TestCase):
    def service(self, conflicts=()):
        collections = FakeCollections(conflicts)
        images = BackgroundImageService(FakeRoomImages(), FakeLights(), collections)
        return CollectionService(collections, images), collections

    def test_room_rejects_lights_already_in_a_room(self):
        service, collections = self.service([{"light_name": "Ceiling", "room_name": "Kitchen"}])
        with self.assertRaisesRegex(ValueError, "Ceiling \\(Kitchen\\)"):
            service.create(GroupCreate(name="Pantry", light_ids=[1]), "room")
        self.assertEqual(collections.added, [])

    def test_groups_ignore_room_conflicts(self):
        service, _ = self.service([{"light_name": "Ceiling", "room_name": "Kitchen"}])
        self.assertEqual(service.create(GroupCreate(name="All", light_ids=[1]), "group")["kind"], "group")

    def test_new_room_infers_image_from_name(self):
        service, _ = self.service()
        room = service.create(GroupCreate(name="Kitchen two", light_ids=[2]), "room")
        self.assertEqual(room["effective_image_url"], VISIA + "k")
        self.assertEqual(room["inference_source"], "room_name")

    def test_wrong_kind_is_not_found(self):
        service, _ = self.service()
        with self.assertRaises(NotFoundError):
            service.rename(7, "group", "Kitchen")


class LightServiceTests(unittest.TestCase):
    def test_discovery_flags_configured_backfills_mac_and_sorts(self):
        lights = FakeLights()
        service = LightService(lights, FakeDiscovery(), None)
        result = asyncio.run(service.discover("192.168.1.255"))
        self.assertEqual([item["ip_address"] for item in result], ["192.168.1.8", "192.168.1.20"])
        self.assertTrue(result[0]["configured"])
        self.assertEqual(lights.macs, [(1, "AA:BB:CC:DD:EE:FF")])
        self.assertEqual(result[0]["suggested_name"], "WiZ light EEFF")
        self.assertEqual(result[1]["suggested_name"], "WiZ light 20")

    def test_discovery_follows_bulbs_that_swapped_ips(self):
        lights = FakeLights([
            {"id": 10, "name": "Balcony", "ip_address": "192.168.1.5", "mac_address": "98:77:D5:D6:D5:FE"},
            {"id": 11, "name": "Entrance", "ip_address": "192.168.1.3", "mac_address": "98:77:D5:D6:8C:66"},
        ])

        class SwappedDiscovery:
            async def scan(self, broadcast_space):
                return [
                    {"ip_address": "192.168.1.3", "mac_address": "9877d5d6d5fe", "protocol": "wiz"},
                    {"ip_address": "192.168.1.5", "mac_address": "9877d5d68c66", "protocol": "wiz"},
                ]

        result = asyncio.run(LightService(lights, SwappedDiscovery(), None).discover("192.168.1.255"))
        self.assertEqual({row["name"]: row["ip_address"] for row in lights.rows},
                         {"Balcony": "192.168.1.3", "Entrance": "192.168.1.5"})
        self.assertEqual(lights.macs, [])
        self.assertTrue(all(item["configured"] for item in result))
        self.assertEqual(result[0]["moved_from"], "192.168.1.5")

    def test_discovery_never_steals_another_lights_mac(self):
        lights = FakeLights([
            {"id": 1, "name": "A", "ip_address": "192.168.1.8", "mac_address": None},
            {"id": 2, "name": "B", "ip_address": "192.168.1.9", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ])

        class Discovery:
            async def scan(self, broadcast_space):
                return [{"ip_address": "192.168.1.8", "mac_address": "aabbccddeeff", "protocol": "wiz"}]

        asyncio.run(LightService(lights, Discovery(), None).discover("192.168.1.255"))
        self.assertEqual(lights.macs, [])

    def test_missing_light_image_is_not_found(self):
        images = BackgroundImageService(FakeRoomImages(), FakeLights(), FakeCollections())
        with self.assertRaises(NotFoundError):
            images.infer_light_image(99)


class SceneServiceTests(unittest.TestCase):
    def test_missing_scene_is_not_found(self):
        class NoScenes:
            def get(self, scene_id): return None
        with self.assertRaises(NotFoundError):
            asyncio.run(SceneService(NoScenes(), None, None, None).apply("all", None, 1))


class HTTPErrorTests(unittest.TestCase):
    def status_and_body(self, error):
        response = LumiaHTTPRoutes.error(error)
        return response.status_code, json.loads(response.body)

    def test_errors_map_to_status_codes(self):
        self.assertEqual(self.status_and_body(NotFoundError("Light not found")), (404, {"error": "Light not found"}))
        self.assertEqual(self.status_and_body(ValueError("bad"))[0], 400)
        self.assertEqual(self.status_and_body(RuntimeError("boom"))[0], 500)
        try:
            LightState(brightness=0)
        except ValidationError as error:
            self.assertEqual(self.status_and_body(error)[0], 422)


if __name__ == "__main__":
    unittest.main()


class RefreshTests(unittest.TestCase):
    def test_subnet_broadcast_uses_the_lights_network(self):
        lights = FakeLights([
            {"id": 1, "name": "A", "ip_address": "192.168.1.8", "mac_address": None},
            {"id": 2, "name": "B", "ip_address": "192.168.1.9", "mac_address": None},
        ])
        self.assertEqual(LightService(lights, None, None).subnet_broadcast(), "192.168.1.255")

    def test_silent_known_bulb_triggers_a_rescan_then_a_second_read(self):
        from app.services.application import LumiaService

        class Control:
            def __init__(self): self.polls = 0
            async def poll_statuses(self):
                self.polls += 1
                ok = self.polls > 1
                return [{"light": {"id": 13, "mac_address": "98:77:D5:D6:9E:A2"}, "ok": ok}]

        class Lights:
            scanned = None
            def subnet_broadcast(self): return "192.168.1.255"
            async def discover(self, space): Lights.scanned = space

        control = Control()
        service = LumiaService(Lights(), None, None, control, None, None, None, None, None)
        result = asyncio.run(service.refresh_lights())
        self.assertEqual((control.polls, Lights.scanned, result[0]["ok"]), (2, "192.168.1.255", True))

    def test_all_answering_needs_no_rescan(self):
        from app.services.application import LumiaService

        class Control:
            async def poll_statuses(self): return [{"light": {"id": 1, "mac_address": "x"}, "ok": True}]

        class Lights:
            async def discover(self, space): raise AssertionError("no scan expected")

        asyncio.run(LumiaService(Lights(), None, None, Control(), None, None, None, None, None).refresh_lights())


class ControlRediscoveryTests(unittest.TestCase):
    """A command to a bulb whose IP changed finds it on the LAN and is sent again."""

    class Lights:
        def __init__(self):
            self.rows = {1: {"id": 1, "name": "A", "ip_address": "192.168.1.8", "mac_address": "aa:bb:cc:dd:ee:01"},
                         2: {"id": 2, "name": "B", "ip_address": "192.168.1.9", "mac_address": "aa:bb:cc:dd:ee:02"}}
        def targets(self, target_type, target_id):
            return [dict(row) for row in self.rows.values() if target_type == "all" or row["id"] == target_id]
        def update_state(self, light_id, **state): return {**self.rows[light_id], **state}

    class Adapter:
        def __init__(self, answering): self.answering, self.sent = answering, []
        async def apply(self, address, **state):
            self.sent.append(address)
            if address not in self.answering:
                raise TimeoutError()

    def service(self, answering, moves_to=None):
        from app.services.application import LightControlService, LumiaService

        lights = self.Lights()
        adapter = self.Adapter(answering)
        control = LightControlService(lights, adapter)

        class Inventory:
            scans = 0
            def subnet_broadcast(self): return "192.168.1.255"
            async def discover(self, space):
                Inventory.scans += 1
                if moves_to:
                    lights.rows[1]["ip_address"] = moves_to

        LumiaService(Inventory(), None, None, control, None, None, None, None, None)
        return control, adapter, Inventory

    def test_a_moved_bulb_is_found_and_sent_the_command_again(self):
        control, adapter, inventory = self.service({"192.168.1.9", "192.168.1.30"}, moves_to="192.168.1.30")
        results = asyncio.run(control.control("all", None, LightState(on=True)))
        self.assertEqual([item["ok"] for item in results], [True, True])
        self.assertEqual(inventory.scans, 1)
        self.assertEqual(adapter.sent.count("192.168.1.9"), 1)  # only the silent light is sent again
        self.assertIn("192.168.1.30", adapter.sent)

    def test_lights_that_answer_cost_no_scan(self):
        control, _, inventory = self.service({"192.168.1.8", "192.168.1.9"})
        asyncio.run(control.control("all", None, LightState(on=True)))
        self.assertEqual(inventory.scans, 0)

    def test_a_bulb_still_silent_after_the_scan_is_reported_and_not_scanned_for_again_soon(self):
        control, _, inventory = self.service({"192.168.1.9"})
        first = asyncio.run(control.control("light", 1, LightState(on=True)))
        asyncio.run(control.control("light", 1, LightState(on=True)))
        self.assertEqual((first[0]["ok"], inventory.scans), (False, 1))
