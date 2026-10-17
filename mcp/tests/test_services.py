import asyncio
import json
import unittest

from pydantic import ValidationError

from app.errors import NotFoundError
from app.http_routes import LumiaHTTPRoutes
from app.models import GroupCreate, LightState
from app.services import (
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
    def __init__(self): self.macs = []
    def list(self): return [{"id": 1, "name": "A", "ip_address": "192.168.1.8", "mac_address": None}]
    def get(self, light_id): return None
    def store_mac_address(self, light_id, mac): self.macs.append((light_id, mac))


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

    def test_missing_light_image_is_not_found(self):
        images = BackgroundImageService(FakeRoomImages(), FakeLights(), FakeCollections())
        with self.assertRaises(NotFoundError):
            images.infer_light_image(99)


class SceneServiceTests(unittest.TestCase):
    def test_missing_scene_is_not_found(self):
        class NoScenes:
            def get(self, scene_id): return None
        with self.assertRaises(NotFoundError):
            asyncio.run(SceneService(NoScenes(), None).apply("all", None, 1))


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
