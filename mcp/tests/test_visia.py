"""Tests for tagging the Luna Visia images Lumia shows."""

import json
import unittest

import httpx

from app.integrations.visia import VisiaImageTagger
from app.services.application import BackgroundImageService
from test_services import FakeCollections, FakeLights, FakeRoomImages

IMAGE_ID = "2d77a066-d097-4b1b-9682-c9eb41538b26"
URL = f"https://visia.example/api/public/images/{IMAGE_ID}"


class VisiaImageTaggerTests(unittest.TestCase):
    def tagger(self, status=200, body=None, token="t" * 32):
        self.requests = []

        def respond(request):
            self.requests.append(request)
            return httpx.Response(status, json=body or {"tagged": [{}], "failed": []})

        return VisiaImageTagger("http://visia/", token, transport=httpx.MockTransport(respond))

    def test_tags_visia_images_luna_lumia(self):
        self.assertEqual(self.tagger().tag(URL.upper().replace("HTTPS://VISIA.EXAMPLE", "https://visia.example")), "tagged")
        request = self.requests[0]
        self.assertEqual(str(request.url), "http://visia/api/companion/images/tags")
        self.assertEqual(json.loads(request.content), {"image_ids": [IMAGE_ID], "tags": ["luna lumia"]})
        self.assertEqual(request.headers["authorization"], f"Bearer {'t' * 32}")

    def test_other_urls_are_left_alone(self):
        tagger = self.tagger()
        for url in (None, "", "https://cdn.example/room.png", "https://visia.example/api/public/images/room.png"):
            self.assertIsNone(tagger.tag(url))
        self.assertEqual(self.requests, [])

    def test_failures_are_reported_not_raised(self):
        with self.assertLogs("app.integrations.visia", "WARNING"):
            self.assertIn("hidden", self.tagger(body={"failed": [{"error": "hidden"}]}).tag(URL))
            self.assertIn("500", self.tagger(status=500).tag(URL))
            self.assertIn("LUNAVISIA_COMPANION_TOKEN", self.tagger(token="").tag(URL))


class RoomPictureTaggingTests(unittest.TestCase):
    def test_explicit_room_pictures_are_tagged(self):
        tagged = []

        class Tagger:
            def tag(self, url):
                tagged.append(url)
                return "tagged"

        images = BackgroundImageService(FakeRoomImages(), FakeLights(), FakeCollections(), Tagger())
        result = images.apply_collection_image(7, URL)
        self.assertEqual((result["visia_tag"], tagged), ("tagged", [URL]))


class StoringPicturesTests(unittest.TestCase):
    def tagger(self, status=200, token="t" * 32):
        self.requests = []

        def respond(request):
            self.requests.append(request)
            if request.url.path.endswith("/tags"):
                return httpx.Response(200, json={"tagged": [{}], "failed": []})
            return httpx.Response(status, json={"status": "stored", "image_id": IMAGE_ID, "public_url": URL, "error": "too big"})

        return VisiaImageTagger("http://visia/", token, transport=httpx.MockTransport(respond))

    def test_a_picture_from_the_page_is_stored_tagged_and_shown(self):
        tagger = self.tagger()
        collections = FakeCollections()
        images = BackgroundImageService(FakeRoomImages(), FakeLights(), collections, tagger)
        result = images.store_image("room", 7, "AAAA")
        stored = json.loads(self.requests[0].content)
        self.assertEqual(str(self.requests[0].url), "http://visia/api/companion/images")
        self.assertEqual(stored, {"name": "kitchen_room", "tags": ["luna lumia", "room", "kitchen"], "content_base64": "AAAA"})
        self.assertEqual(result["background_image_url"], URL)

    def test_a_picture_needs_its_item_visia_and_the_token(self):
        from app.core.errors import NotFoundError

        images = BackgroundImageService(FakeRoomImages(), FakeLights(), FakeCollections(), self.tagger())
        with self.assertRaises(NotFoundError):
            images.store_image("group", 7, "AAAA")  # 7 is a room
        with self.assertRaises(NotFoundError):
            images.store_image("light", 99, "AAAA")
        with self.assertRaisesRegex(ValueError, "LUNAVISIA_COMPANION_TOKEN"):
            BackgroundImageService(FakeRoomImages(), FakeLights(), FakeCollections(), self.tagger(token="")).store_image("room", 7, "AAAA")
        with self.assertRaisesRegex(ValueError, "too big"):
            BackgroundImageService(FakeRoomImages(), FakeLights(), FakeCollections(), self.tagger(status=413)).store_image("room", 7, "AAAA")


if __name__ == "__main__":
    unittest.main()
