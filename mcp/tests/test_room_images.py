import unittest

from app.room_images import ImageScheme, RoomImageCatalog, RoomKeyDetector

VISIA = "https://visia.example/api/public/images/"
OTHER = "https://other.example/rooms/"


class RoomKeyDetectorTests(unittest.TestCase):
    def test_unknown_names_fall_back_to_living_room(self):
        self.assertEqual(RoomKeyDetector.for_name("Downstairs"), "living_room")

    def test_member_names_use_first_detected_room(self):
        self.assertEqual(
            RoomKeyDetector.for_member_names(["Lamp", "Desk light", "Bed light"]),
            "home_office",
        )
        self.assertIsNone(RoomKeyDetector.for_member_names(["Lamp"]))


class RoomImageCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = RoomImageCatalog(
            [
                {"room_key": "kitchen", "image_url": OTHER + "kitchen.png"},
                {"room_key": "kitchen", "image_url": VISIA + "k1"},
                {"room_key": "living_room", "image_url": VISIA + "l1"},
            ]
        )

    def test_url_for_unknown_room_uses_living_room(self):
        self.assertEqual(self.catalog.url_for("bathroom"), VISIA + "l1")

    def test_select_prefers_room_in_preferred_scheme(self):
        self.assertEqual(self.catalog.select("kitchen", VISIA)["image_url"], VISIA + "k1")
        self.assertEqual(
            self.catalog.select("kitchen", OTHER)["image_url"], OTHER + "kitchen.png"
        )

    def test_select_falls_back_to_living_room_in_same_scheme(self):
        self.assertEqual(self.catalog.select("bedroom", VISIA)["image_url"], VISIA + "l1")

    def test_scheme_counts_ignore_missing_urls(self):
        counts = self.catalog.scheme_counts([None, VISIA + "x"])
        self.assertEqual(counts[ImageScheme.key(VISIA + "x")], 3)


if __name__ == "__main__":
    unittest.main()
