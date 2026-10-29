import asyncio
import unittest
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.core.models import MUSIC_MOODS, MusicAutomationUpdate, MusicSlot
from app.integrations.vibia import VibiaPlayback, VibiaUnavailableError
from app.services.music import MusicMoods, MusicService
from app.services.presets import MUSIC_SEQUENCES, MUSIC_SOLIDS, MusicPresets
from app.services.workers import WeatherWorker
from app.transport.mcp_tools import LumiaMCPTools
from tests.test_weather import FakeAutomation, FakeServer

# Tags and captions as Luna Vibia wrote them for real tracks.
MIDNIGHT_WHISPERS = {
    "name": "Midnight_Whispers.mp3",
    "tags": ["ambient", "piano", "sleep", "melancholic", "slow", "pads", "meditation"],
    "caption": "dreamy ambient piano solo with warm pads, slow tempo for sleep or meditation",
}
RAINY_CAFE = {
    "name": "Rainy_Cafe_Instrumental.mp3",
    "tags": ["acoustic folk", "piano", "meditation", "focus", "relaxed", "caf", "instrumental"],
    "caption": "gentle acoustic folk instrumental with warm piano; relaxed tempo for focus or meditation",
}
CAFE_WALTZ = {"name": "Cafe_Waltz.mp3", "tags": ["romantic", "vintage", "jazz-pop", "caf"], "caption": ""}
SUNSHINE = {"name": "Cafe_Sunshine_Soul.mp3", "tags": ["soul-pop", "happy", "cafe", "uplifting"], "caption": ""}


class FakeVibia:
    def __init__(self): self.playing = None

    def status(self):
        if self.playing is None:
            return {"status": "idle"}
        return {"status": "playing", "now_playing": self.playing["name"], "track": self.playing}


class FakeMusicSlots:
    def __init__(self, scenes): self.scenes, self.rows = scenes, {}

    def list(self):
        names = {scene["id"]: scene for scene in self.scenes.rows}
        return [
            {"mood": mood, "scene_id": scene_id,
             "scheme_name": names[scene_id]["name"] if scene_id else None,
             "scheme_kind": names[scene_id]["kind"] if scene_id else None}
            for mood, scene_id in self.rows.items()
        ]

    def set(self, mood, scene_id): self.rows[mood] = scene_id


class FakeSceneRepository:
    """Every built-in music scheme plus one user scheme (id 100)."""

    def __init__(self):
        names = [name for name, *_ in MUSIC_SOLIDS] + list(MUSIC_SEQUENCES)
        self.rows = [{"id": i, "name": n, "kind": "sequence", "is_preset": True} for i, n in enumerate(names, 1)]
        self.rows.append({"id": 100, "name": "My night", "kind": "sequence", "is_preset": False})

    def list(self): return self.rows


class FakeScenes:
    def __init__(self):
        self.scenes = FakeSceneRepository()
        self.applied = []

    def get(self, scene_id):
        if scene_id not in {row["id"] for row in self.scenes.rows}:
            raise LookupError("Scene not found")
        return {"id": scene_id}

    async def apply(self, target_type, target_id, scene_id):
        self.applied.append((target_type, target_id, scene_id))
        return {"scene": scene_id, "target_type": target_type}


class FakeWeather:
    def __init__(self): self.reapplied, self.followed = 0, 0
    def reapply(self): self.reapplied += 1
    def follow(self, moment): self.followed += 1


def music_service():
    scenes = FakeScenes()
    return MusicService(FakeVibia(), FakeMusicSlots(scenes.scenes), FakeAutomation(), scenes, FakeWeather())


class MusicMoodTests(unittest.TestCase):
    def test_night_music_is_sleep_even_when_tagged_melancholic(self):
        mood = MusicMoods.classify(MIDNIGHT_WHISPERS)
        self.assertEqual((mood["mood"], mood["matched"], mood["from"]), ("sleep", ["sleep"], "tags"))

    def test_cafe_tracks_get_their_own_moods(self):
        # "meditation" on a café track is not sleep; "caf" is a tag cut at its accent.
        self.assertEqual(MusicMoods.classify(RAINY_CAFE)["mood"], "cozy")
        self.assertEqual(MusicMoods.classify(CAFE_WALTZ)["mood"], "romantic")
        self.assertEqual(MusicMoods.classify(SUNSHINE)["mood"], "upbeat")

    def test_caption_is_used_when_no_tag_matches_and_calm_is_the_fallback(self):
        from_caption = MusicMoods.classify({"tags": ["piano"], "caption": "a lullaby for babies"})
        self.assertEqual((from_caption["mood"], from_caption["from"]), ("sleep", "caption"))
        self.assertEqual(MusicMoods.classify({"tags": ["piano"], "caption": ""})["mood"], "calm")

    def test_words_match_whole_words_only(self):
        # "house" inside "lighthouse" must not count as energetic.
        self.assertEqual(MusicMoods.classify({"tags": ["lighthouse"], "caption": ""})["mood"], "calm")

    def test_slot_validation(self):
        self.assertEqual(MusicSlot(mood=" Sleep ").mood, "sleep")
        with self.assertRaises(ValidationError):
            MusicSlot(mood="spooky")
        with self.assertRaises(ValidationError):
            MusicAutomationUpdate(enabled=True, target_type="light")


class MusicPresetTests(unittest.TestCase):
    def test_every_mood_has_a_built_in_scheme(self):
        names = {name for name, *_ in MUSIC_SOLIDS} | set(MUSIC_SEQUENCES)
        self.assertEqual({MusicPresets.name(mood) for mood in MUSIC_MOODS}, names)

    def test_sleep_is_soft_light_blue_with_long_smooth_fades(self):
        loops, steps = MUSIC_SEQUENCES["Music · Sleep"]
        self.assertTrue(loops)
        for color, brightness, _, transition in steps:
            red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            self.assertTrue(blue > green > red, color)
            self.assertLessEqual(brightness, 25)
            self.assertEqual(transition, "Long fade")


class MusicServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = music_service()

    def test_current_names_the_track_mood_and_scheme(self):
        self.assertEqual(self.service.current(), {"playing": False, "status": "idle"})
        self.service.vibia.playing = MIDNIGHT_WHISPERS
        music = self.service.current()
        self.assertEqual((music["track"], music["mood"]), ("Midnight_Whispers.mp3", "sleep"))
        self.assertEqual(music["scheme"]["name"], "Music · Sleep")

    def test_assigned_scheme_replaces_the_built_in_until_reset(self):
        self.service.set_slot("sleep", 100)
        self.assertEqual(self.service.slot("sleep")["scheme"]["name"], "My night")
        self.assertFalse(self.service.slot("sleep")["is_built_in"])
        self.service.reset_slots("sleep")
        self.assertTrue(self.service.slot("sleep")["is_built_in"])
        with self.assertRaises(LookupError):
            self.service.set_slot("sleep", 999)

    def test_decorate_marks_schemes_used_for_music(self):
        schemes = self.service.decorate([{"id": 100}, {"id": self.service.slot("sleep")["scheme"]["id"]}])
        self.assertEqual([scheme["music_moods"] for scheme in schemes], [[], ["sleep"]])

    def test_apply_uses_the_playing_mood_or_the_one_given(self):
        with self.assertRaises(ValueError):
            asyncio.run(self.service.apply_current())
        asyncio.run(self.service.apply_current("group", 3, mood="sleep"))
        self.service.vibia.playing = CAFE_WALTZ
        result = asyncio.run(self.service.apply_current())
        romantic = self.service.slot("romantic")["scheme"]["id"]
        self.assertEqual(self.service.scenes.applied[-1], ("all", None, romantic))
        self.assertEqual(result["music"]["mood"], "romantic")

    def test_automation_applies_once_per_mood_and_hands_back_to_the_weather(self):
        service, scenes = self.service, self.service.scenes
        service.vibia.playing = MIDNIGHT_WHISPERS
        service.follow()
        self.assertEqual(scenes.applied, [])  # off by default
        service.set_automation(MusicAutomationUpdate(enabled=True, target_type="on"))
        service.follow()
        service.follow()
        service.vibia.playing = {**MIDNIGHT_WHISPERS, "name": "Gentle_Sleep_Ambient.mp3"}
        service.follow()  # another sleep track: lights keep going
        self.assertEqual(len(scenes.applied), 1)
        self.assertTrue(service.holds_lights())
        service.vibia.playing = RAINY_CAFE
        service.follow()
        self.assertEqual(scenes.applied[-1][2], service.slot("cozy")["scheme"]["id"])
        service.vibia.playing = None
        service.follow()
        self.assertFalse(service.holds_lights())
        self.assertEqual(service.weather.reapplied, 1)
        self.assertEqual(len(scenes.applied), 2)

    def test_weather_waits_while_music_holds_the_lights(self):
        service = self.service
        worker = WeatherWorker(service.weather, ZoneInfo("Asia/Kolkata"), 60, service)
        service.set_automation(MusicAutomationUpdate(enabled=True))
        service.vibia.playing = MIDNIGHT_WHISPERS
        service.follow()
        worker.tick()
        self.assertEqual(service.weather.followed, 0)
        service.vibia.playing = None
        service.follow()
        worker.tick()
        self.assertEqual(service.weather.followed, 1)

    def test_unreachable_vibia_is_reported_not_raised(self):
        service = music_service()
        service.vibia = VibiaPlayback("http://luna-vibia-mcp:8000", "")
        self.assertIn("LUNAVIBIA_API_TOKEN", service.now()["music"]["error"])
        service.set_automation(MusicAutomationUpdate(enabled=True))
        service.follow()  # silently waits for Vibia
        with self.assertRaises(VibiaUnavailableError):
            service.current()


class MusicToolTests(unittest.TestCase):
    def setUp(self):
        self.music = music_service()
        service = type("Service", (), {})()
        service.music = self.music
        for name in ("lights", "collections", "images", "control", "scenes", "transitions", "schedules", "weather"):
            setattr(service, name, object())
        self.server = FakeServer()
        LumiaMCPTools(self.server, service)

    def test_music_tools_are_registered(self):
        expected = {
            "get_music", "list_music_schemes", "set_music_scheme", "reset_music_schemes",
            "apply_music_scheme", "set_music_automation",
        }
        self.assertTrue(expected.issubset(self.server.tools))

    def test_follow_the_night_loop_from_the_tools(self):
        tools = self.server.tools
        self.music.vibia.playing = MIDNIGHT_WHISPERS
        self.assertEqual(tools["get_music"]()["music"]["mood"], "sleep")
        with self.assertRaises(ValidationError):
            tools["set_music_scheme"]("spooky", 100)
        tools["set_music_scheme"]("Sleep", 100)
        asyncio.run(tools["apply_music_scheme"]())
        self.assertEqual(self.music.scenes.applied[-1], ("all", None, 100))
        tools["reset_music_schemes"]()
        self.assertTrue(all(row["is_built_in"] for row in tools["list_music_schemes"]()))


if __name__ == "__main__":
    unittest.main()
