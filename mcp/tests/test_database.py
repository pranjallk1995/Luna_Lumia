import unittest

from app.data.database import SCHEMA_SQL


class CollectionSchemaTests(unittest.TestCase):
    def test_only_room_memberships_are_unique_per_light(self):
        self.assertIn("membership_kind TEXT NOT NULL DEFAULT 'room'", SCHEMA_SQL)
        self.assertIn(
            "ON group_members (light_id) WHERE membership_kind = 'room'",
            SCHEMA_SQL,
        )
        self.assertNotIn("ON group_members (light_id);", SCHEMA_SQL)

    def test_existing_collections_migrate_as_rooms(self):
        self.assertIn("kind TEXT NOT NULL DEFAULT 'room'", SCHEMA_SQL)
        self.assertIn("SET membership_kind = lg.kind", SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
