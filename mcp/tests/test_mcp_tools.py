import asyncio
import unittest

from app.transport.mcp_tools import LumiaMCPTools


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class FakeScenes:
    def __init__(self):
        self.applied = []
        self.stopped = []
        self.deleted = []

    def list(self):
        return [{"id": 7, "name": "Sunset"}]

    def playing(self):
        return {3: 7}

    async def apply(self, target_type, target_id, scheme_id):
        self.applied.append((target_type, target_id, scheme_id))
        return {"scheme": "Sunset"}

    def stop(self, target_type, target_id):
        self.stopped.append((target_type, target_id))
        return {"stopped_light_ids": [3]}

    def delete(self, scheme_id):
        self.deleted.append(scheme_id)


class FakeTransitions:
    def __init__(self):
        self.deleted = []

    def list(self):
        return [{"id": 2, "name": "Smooth"}]

    def delete(self, transition_id):
        self.deleted.append(transition_id)


class FakeCollections:
    def __init__(self):
        self.calls = []

    def list_with_images(self, kind):
        self.calls.append(("list", kind))
        return [{"id": 1, "kind": kind}]

    def get(self, collection_id, kind):
        self.calls.append(("get", collection_id, kind))
        return {"id": collection_id, "kind": kind}

    def rename(self, collection_id, kind, name):
        self.calls.append(("rename", collection_id, kind, name))
        return {"id": collection_id, "kind": kind, "name": name}

    def add_members(self, collection_id, kind, light_ids):
        self.calls.append(("add", collection_id, kind, light_ids))
        return {"id": collection_id, "kind": kind, "light_ids": light_ids}

    def remove_member(self, collection_id, kind, light_id):
        self.calls.append(("remove", collection_id, kind, light_id))

    def delete(self, collection_id, kind):
        self.calls.append(("delete", collection_id, kind))


class FakeService:
    def __init__(self):
        self.scenes = FakeScenes()
        self.transitions = FakeTransitions()
        self.lights = object()
        self.collections = FakeCollections()
        self.images = object()
        self.control = object()


class SchemeMCPToolTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer()
        self.service = FakeService()
        LumiaMCPTools(self.server, self.service)

    def test_scheme_management_tools_are_registered(self):
        expected = {
            "list_schemes",
            "create_solid_scheme",
            "create_sequence_scheme",
            "apply_scheme",
            "stop_scheme",
            "delete_scheme",
            "create_transition",
            "delete_transition",
        }
        self.assertTrue(expected.issubset(self.server.tools))

    def test_apply_and_stop_scheme_delegate_to_scene_service(self):
        result = asyncio.run(self.server.tools["apply_scheme"](7, "group", 4))
        stopped = self.server.tools["stop_scheme"]("light", 3)
        self.assertEqual(result, {"scheme": "Sunset"})
        self.assertEqual(stopped, {"stopped_light_ids": [3]})
        self.assertEqual(self.service.scenes.applied, [("group", 4, 7)])
        self.assertEqual(self.service.scenes.stopped, [("light", 3)])

    def test_delete_tools_return_confirmation(self):
        scheme = self.server.tools["delete_scheme"](7)
        transition = self.server.tools["delete_transition"](2)
        self.assertEqual(scheme, {"deleted": True, "scheme_id": 7})
        self.assertEqual(transition, {"deleted": True, "transition_id": 2})
        self.assertEqual(self.service.scenes.deleted, [7])
        self.assertEqual(self.service.transitions.deleted, [2])


class CollectionMCPToolTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer()
        self.service = FakeService()
        LumiaMCPTools(self.server, self.service)

    def test_room_and_group_management_tools_are_registered(self):
        expected = {
            "list_rooms", "list_groups", "get_room", "get_group",
            "create_room", "create_group", "rename_room", "rename_group",
            "add_lights_to_room", "add_lights_to_group",
            "remove_light_from_room", "remove_light_from_group",
            "delete_room", "delete_group",
        }
        self.assertTrue(expected.issubset(self.server.tools))

    def test_room_tools_use_room_kind_and_return_confirmations(self):
        self.assertEqual(self.server.tools["list_rooms"](), [{"id": 1, "kind": "room"}])
        renamed = self.server.tools["rename_room"](4, "Bedroom")
        added = self.server.tools["add_lights_to_room"](4, [8, 9])
        removed = self.server.tools["remove_light_from_room"](4, 8)
        deleted = self.server.tools["delete_room"](4)
        self.assertEqual(renamed["name"], "Bedroom")
        self.assertEqual(added["light_ids"], [8, 9])
        self.assertEqual(removed, {"removed": True, "room_id": 4, "light_id": 8})
        self.assertEqual(deleted, {"deleted": True, "room_id": 4})

    def test_group_tools_use_group_kind(self):
        self.server.tools["list_groups"]()
        self.server.tools["get_group"](6)
        self.server.tools["rename_group"](6, "Downstairs")
        self.server.tools["add_lights_to_group"](6, [8])
        self.server.tools["remove_light_from_group"](6, 8)
        self.server.tools["delete_group"](6)
        kinds = [call[2] for call in self.service.collections.calls if call[0] != "list"]
        self.assertEqual(kinds, ["group"] * 5)


if __name__ == "__main__":
    unittest.main()
