"""Light the room for the music Luna Vibia plays: each track's mood picks a scheme."""

from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from app.core.models import MusicAutomationUpdate, MusicBeatsUpdate
from app.data.repositories import MusicAutomationRepository, MusicSchemeRepository, Row
from app.integrations.vibia import VibiaPlayback, VibiaUnavailableError
from app.services.application import SceneService, WeatherService
from app.services.playback import BeatClock
from app.services.presets import MusicPresets

LOG = logging.getLogger("uvicorn.error")


def run_sync(coroutine):
    """Run a coroutine to completion from sync code, called inside an event loop or not."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


class MusicMoods:
    """Read a track's mood from the tags and caption Luna Vibia wrote for it.

    Moods are checked in priority order and the first whose words appear wins:
    all the tags first, then the caption. Sleep comes first, so a sleep track
    tagged "melancholic" or "focus" too still gets the sleep scheme; calm is the
    fallback. Vibia's energy and tempo are not used: energy measures loudness
    and reads high for quiet music, and the tempo of slow pieces is often doubled.
    """

    WORDS: dict[str, tuple[str, ...]] = {
        "sleep": ("sleep", "sleepy", "sleeping", "lullaby", "bedtime", "slumber", "nocturne", "insomnia"),
        "energetic": (
            "energetic", "dance", "edm", "house", "techno", "trance", "rock", "metal", "punk",
            "workout", "gym", "party", "hype", "drum and bass", "dnb", "dubstep", "intense",
        ),
        "romantic": ("romantic", "romance", "love", "valentine", "candlelight", "intimate"),
        "upbeat": (
            "upbeat", "happy", "cheerful", "joyful", "uplifting", "feel-good", "groovy",
            "funk", "funky", "disco", "sunny", "playful",
        ),
        "melancholic": (
            "melancholic", "melancholy", "sad", "sorrowful", "heartbreak", "lonely",
            "bittersweet", "nostalgic", "somber", "dark",
        ),
        "cozy": (
            "café", "cafe", "caf", "coffee", "jazz", "jazz-pop", "jazzy", "bossa nova", "bossa",
            "acoustic", "cozy", "brunch", "vintage",
        ),
        "focus": ("focus", "study", "studying", "concentration", "lo-fi", "lofi", "productivity", "coding"),
        "calm": (
            "calm", "relaxing", "relaxed", "relax", "chill", "chillout", "peaceful", "tranquil",
            "serene", "ambient", "soothing", "gentle", "downtempo", "spa",
        ),
    }
    FALLBACK = "calm"

    @staticmethod
    def pattern(word: str) -> re.Pattern[str]:
        # Whole words, so "caf" (a tag cut at its accent) does not match inside "cafe".
        return re.compile(rf"(?<![\w-]){re.escape(word)}(?![\w-])")

    @classmethod
    def classify(cls, track: Row) -> Row:
        """The mood, and the words that decided it (None when nothing matched)."""
        tags = " | ".join(str(tag).lower() for tag in track.get("tags") or [])
        caption = str(track.get("caption") or "").lower()
        for source, text in (("tags", tags), ("caption", caption)):
            for mood, words in cls.WORDS.items():
                matched = [word for word in words if cls.pattern(word).search(text)]
                if matched:
                    return {"mood": mood, "matched": matched, "from": source}
        return {"mood": cls.FALLBACK, "matched": None, "from": None}


class MusicService:
    """Pick a scheme for the mood of the track Luna Vibia plays, and follow it.

    Every mood has a scheme, starting with its built-in "Music · ..." one. While
    the automation is on and music plays, it applies the mood's scheme once each
    time the mood (or its scheme) changes, and weather automation waits; when the
    music stops, the lights are left as they are and the weather takes over again.

    With beats on, moods that pulse (see ``MusicPresets.BEAT_DEPTH``) play their
    scheme's colors as pulses on each track's beats instead, timed by Vibia's
    playback clock; when the music stops the pulses end and the scheme plays on.
    """

    BEAT_MAPS_KEPT = 32

    def __init__(
        self,
        vibia: VibiaPlayback,
        slots: MusicSchemeRepository,
        automation: MusicAutomationRepository,
        scenes: SceneService,
        weather: WeatherService,
    ) -> None:
        self.vibia = vibia
        self.slots = slots
        self.automation_settings = automation
        self.scenes = scenes
        self.weather = weather
        self._beat_maps: dict[str, Row] = {}
        # The beat pulses playing now: their key, track start, scheme, and target.
        self._pulsing: Row | None = None

    # Moods and their schemes

    def slot_list(self) -> list[Row]:
        """Every mood with its scheme; an empty mood falls back to the built-in."""
        presets = {row["name"]: row for row in self.scenes.scenes.list() if row["is_preset"]}
        saved = {row["mood"]: row for row in self.slots.list()}
        rows = []
        for mood in MusicPresets.moods():
            built_in = presets.get(MusicPresets.name(mood))
            row = saved.get(mood)
            if row and row["scene_id"] is not None:
                scheme = {"id": row["scene_id"], "name": row["scheme_name"], "kind": row["scheme_kind"]}
            elif built_in:
                scheme = {"id": built_in["id"], "name": built_in["name"], "kind": built_in["kind"]}
            else:
                scheme = None
            rows.append({
                "mood": mood,
                "words": list(MusicMoods.WORDS[mood]),
                "scheme": scheme,
                "is_built_in": bool(scheme and built_in and scheme["id"] == built_in["id"]),
                "built_in_scheme_id": built_in["id"] if built_in else None,
            })
        return rows

    def slot(self, mood: str) -> Row:
        return next(row for row in self.slot_list() if row["mood"] == mood)

    def set_slot(self, mood: str, scene_id: int) -> Row:
        self.scenes.get(scene_id)
        self.slots.set(mood, scene_id)
        return self.slot(mood)

    def reset_slots(self, mood: str | None = None) -> list[Row]:
        """Point one mood (all when None) back at its built-in scheme."""
        for row in self.slot_list():
            if mood in (None, row["mood"]):
                self.slots.set(row["mood"], row["built_in_scheme_id"])
        return self.slot_list()

    def decorate(self, schemes: list[Row]) -> list[Row]:
        """Add ``music_moods`` (e.g. ["sleep"]) to each scheme used for the music."""
        used: dict[int, list[str]] = {}
        for row in self.slot_list():
            if row["scheme"]:
                used.setdefault(row["scheme"]["id"], []).append(row["mood"])
        for scheme in schemes:
            scheme["music_moods"] = used.get(scheme["id"], [])
        return schemes

    # The music now

    def current(self) -> Row:
        """What Vibia plays, its mood, and the scheme for it; ``playing`` False when idle."""
        status = self.vibia.status()
        track = status.get("track")
        if status.get("status") != "playing" or not track:
            return {"playing": False, "status": status.get("status")}
        mood = MusicMoods.classify(track)
        return {
            "playing": True,
            "track": track["name"],
            "title": track.get("title"),
            "tags": track.get("tags"),
            "started_at": status.get("started_at"),
            **mood,
            "scheme": self.slot(mood["mood"])["scheme"],
            "beat_depth": MusicPresets.BEAT_DEPTH[mood["mood"]],
        }

    def now(self) -> Row:
        """The music now (or why it is unknown) and the automation setting."""
        try:
            music = self.current()
        except VibiaUnavailableError as error:
            music = {"playing": False, "error": str(error)}
        return {"music": music, "automation": self.automation(), "beats": self.beat_settings()}

    async def apply_current(
        self, target_type: str = "all", target_id: int | None = None, mood: str | None = None
    ) -> Row:
        """Apply the scheme for the playing track's mood, or for ``mood`` when given."""
        if mood is None:
            music = self.current()
            if not music["playing"]:
                raise ValueError("Luna Vibia is not playing anything; pass a mood to light for one anyway")
            mood = music["mood"]
        else:
            music = {"mood": mood}
        scheme = self.slot(mood)["scheme"]
        if scheme is None:
            raise ValueError(f"No scheme for {mood} music")
        applied = await self.scenes.apply(target_type, target_id, scheme["id"])
        return {"music": music, **applied}

    # Automation

    def automation(self) -> Row:
        return self.automation_settings.get()

    def set_automation(self, entry: MusicAutomationUpdate) -> Row:
        if entry.target_type in ("light", "group"):
            self.scenes.control.resolve_targets(entry.target_type, entry.target_id)
        self._end_pulses()
        saved = self.automation_settings.save(entry)
        if not entry.enabled:
            self.weather.reapply()
        return {**saved, **self.now()}

    def beat_settings(self) -> Row:
        return self.automation_settings.beats()

    def set_beats(self, entry: MusicBeatsUpdate) -> Row:
        """Turn beat pulses on or off, or change their timing or strength."""
        current = self.beat_settings()
        saved = self.automation_settings.save_beats(
            entry.enabled,
            current["offset_ms"] if entry.offset_ms is None else entry.offset_ms,
            current["strength"] if entry.strength is None else entry.strength,
        )
        if self.automation()["last_applied"]:
            # Re-apply on the next tick, without letting the weather in meanwhile.
            self.automation_settings.mark_applied("beat settings changed")
        return {**saved, **self.now()}

    def holds_lights(self) -> bool:
        """Whether the music automation lit the lights for music that is still playing."""
        settings = self.automation()
        return bool(settings["enabled"] and settings["last_applied"])

    def follow(self) -> None:
        """Apply the mood's scheme once each time the mood or its scheme changes."""
        settings = self.automation()
        if not settings["enabled"]:
            return
        try:
            music = self.current()
        except VibiaUnavailableError:
            return
        if not music["playing"]:
            if settings["last_applied"]:
                # The music stopped: leave the lights, and let the weather decide again.
                self._end_pulses()
                self.automation_settings.mark_applied(None)
                self.weather.reapply()
            return
        if music["scheme"] is None:
            return
        beats = self.beat_settings()
        depth = min(1.0, music["beat_depth"] * beats["strength"])
        if beats["enabled"] and depth > 0 and music.get("started_at"):
            self._follow_beats(settings, music, beats, depth)
            return
        key = f'{music["mood"]}|{music["scheme"]["id"]}'
        if key == settings["last_applied"]:
            return
        self._pulsing = None
        LOG.info("Music %r is %s; applying %r", music["track"], music["mood"], music["scheme"]["name"])
        asyncio.run(self.scenes.apply(settings["target_type"], settings["target_id"], music["scheme"]["id"]))
        self.automation_settings.mark_applied(key)

    def beat_map(self, name: str) -> Row:
        """A track's beat map from Vibia, kept for the tracks played most recently."""
        if name not in self._beat_maps:
            if len(self._beat_maps) >= self.BEAT_MAPS_KEPT:
                self._beat_maps.pop(next(iter(self._beat_maps)))
            self._beat_maps[name] = self.vibia.beats(name)
        return self._beat_maps[name]

    def _follow_beats(self, settings: Row, music: Row, beats: Row, depth: float) -> None:
        """Start pulses for a new track, scheme, or setting, or when the track restarted
        or moved (a speaker switch resumes it with a new start time)."""
        key = f'beats|{music["track"]}|{music["scheme"]["id"]}|{beats["offset_ms"]}|{depth:.2f}'
        pulsing = self._pulsing
        if (
            pulsing and pulsing["key"] == key and key == settings["last_applied"]
            and abs(pulsing["started_at"] - music["started_at"]) < 0.25
        ):
            return
        try:
            beat_map = self.beat_map(music["track"])
        except VibiaUnavailableError:
            return
        clock = BeatClock(
            beats=tuple(beat_map["beats"]),
            strengths=tuple(beat_map["strengths"]),
            started_at=music["started_at"],
            offset_s=beats["offset_ms"] / 1000,
            depth=depth,
            duration_s=beat_map.get("duration_seconds") or (beat_map["beats"][-1] + 1 if beat_map["beats"] else 0),
        )
        target = (settings["target_type"], settings["target_id"])
        LOG.info("Music %r is %s; pulsing %r on its beats", music["track"], music["mood"], music["scheme"]["name"])
        self.scenes.play_beats(*target, music["scheme"]["id"], clock)
        self._pulsing = {"key": key, "started_at": music["started_at"], "scheme_id": music["scheme"]["id"], "target": target}
        self.automation_settings.mark_applied(key)

    def _end_pulses(self) -> None:
        """Replace any beat pulses with their scheme, so the lights do not stop mid-pulse."""
        pulsing, self._pulsing = self._pulsing, None
        if pulsing:
            run_sync(self.scenes.apply(*pulsing["target"], pulsing["scheme_id"]))
