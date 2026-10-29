"""Built-in transitions and schemes, installed (or refreshed) at startup."""

from __future__ import annotations

from typing import Any

from app.core.models import DAYPARTS, MUSIC_MOODS, WEATHER_CONDITIONS, SceneCreate, SceneStep, TransitionCreate
from app.data.repositories import (
    MusicSchemeRepository,
    SceneRepository,
    TransitionRepository,
    WeatherSchemeRepository,
)

TRANSITIONS = (
    TransitionCreate(name="Instant", duration_ms=0, curve="linear"),
    TransitionCreate(name="Flicker", duration_ms=150, curve="linear"),
    TransitionCreate(name="Quick fade", duration_ms=400, curve="ease-out"),
    TransitionCreate(name="Smooth", duration_ms=1_500, curve="ease-in-out"),
    TransitionCreate(name="Slow fade", duration_ms=5_000, curve="ease-in-out"),
    TransitionCreate(name="Long fade", duration_ms=60_000, curve="linear"),
)

# Solid schemes: (name, color or Kelvin temperature, brightness %).
SOLIDS = (
    ("Focus", 5000, 100),
    ("Daylight", 6500, 100),
    ("Reading", 4000, 85),
    ("Bedtime", 2200, 25),
    ("Warm evening", "#FFB36B", 55),
    ("Night light", "#FF6B3D", 12),
)

# Sequences: name -> (loops, steps of (color or Kelvin, brightness %, hold ms, transition)).
SEQUENCES: dict[str, tuple[bool, tuple]] = {
    "Pulse": (True, (
        (2700, 100, 300, "Smooth"),
        (2700, 15, 300, "Smooth"),
    )),
    "Candle light": (True, (
        ("#FF9329", 70, 250, "Flicker"),
        ("#FF7A1A", 45, 120, "Flicker"),
        ("#FFA040", 62, 350, "Flicker"),
        ("#FF8A26", 50, 180, "Flicker"),
        ("#FF9A30", 68, 220, "Flicker"),
    )),
    "Fireplace": (True, (
        ("#FF4500", 85, 500, "Quick fade"),
        ("#FF7F24", 60, 300, "Quick fade"),
        ("#FF5A00", 95, 450, "Quick fade"),
        ("#E63E00", 55, 350, "Quick fade"),
        ("#FF6A10", 75, 400, "Quick fade"),
    )),
    "Party": (True, (
        ("#FF2D55", 100, 600, "Instant"),
        ("#FFD60A", 100, 600, "Instant"),
        ("#32D74B", 100, 600, "Instant"),
        ("#0A84FF", 100, 600, "Instant"),
        ("#BF5AF2", 100, 600, "Instant"),
    )),
    "Ocean": (True, (
        ("#0A84FF", 60, 1_000, "Slow fade"),
        ("#00C7BE", 75, 1_000, "Slow fade"),
        ("#5AC8FA", 55, 1_000, "Slow fade"),
        ("#30B0C7", 70, 1_000, "Slow fade"),
    )),
    "Sunrise": (False, (
        ("#FF3B1F", 5, 0, "Instant"),
        ("#FF7A33", 35, 0, "Long fade"),
        (2700, 70, 0, "Long fade"),
        (4500, 100, 0, "Long fade"),
    )),
}


# Weather schemes: one per (condition, day/night). By day they stand in for the
# light outside (cooler and brighter when clear, warmer when grey); by night they
# stay warm and dim. Rain drifts slowly; thunderstorms add brief lightning flashes.
WEATHER_SOLIDS = (
    ("Weather · Clear day", 5500, 100),
    ("Weather · Clear night", 2700, 50),
    ("Weather · Partly cloudy day", 4800, 95),
    ("Weather · Partly cloudy night", 2600, 45),
    ("Weather · Cloudy day", 4200, 90),
    ("Weather · Cloudy night", 2500, 40),
    ("Weather · Fog day", 3800, 85),
    ("Weather · Fog night", "#FFC98A", 35),
    ("Weather · Snow day", 6000, 95),
    ("Weather · Snow night", "#FFD7A8", 40),
)
WEATHER_SEQUENCES: dict[str, tuple[bool, tuple]] = {
    "Weather · Rain day": (True, (
        (3500, 80, 20_000, "Long fade"),
        ("#A9C1D9", 70, 20_000, "Long fade"),
    )),
    "Weather · Rain night": (True, (
        ("#FF9F5A", 40, 20_000, "Long fade"),
        ("#E07A4F", 32, 20_000, "Long fade"),
    )),
    "Weather · Thunderstorm day": (True, (
        (3200, 65, 12_000, "Slow fade"),
        (6500, 100, 80, "Instant"),
        (3200, 65, 150, "Flicker"),
        (6500, 100, 60, "Instant"),
        (3200, 65, 20_000, "Flicker"),
    )),
    "Weather · Thunderstorm night": (True, (
        ("#FF8A3D", 35, 15_000, "Slow fade"),
        ("#DDE6FF", 80, 80, "Instant"),
        ("#FF8A3D", 35, 150, "Flicker"),
        ("#DDE6FF", 70, 60, "Instant"),
        ("#FF8A3D", 35, 25_000, "Flicker"),
    )),
}


# Music schemes: one per mood of the track Luna Vibia plays. Quiet moods are dim with
# long, smooth fades (sleep: soft light blues that drift over minutes); lively ones
# are brighter and change faster, up to quick vivid colour changes for energetic music.
MUSIC_SOLIDS = (
    ("Music · Focus", 4000, 80),
)
MUSIC_SEQUENCES: dict[str, tuple[bool, tuple]] = {
    "Music · Sleep": (True, (
        ("#9DBEFF", 20, 10_000, "Long fade"),
        ("#B8D4FF", 14, 10_000, "Long fade"),
        ("#86AEEB", 18, 10_000, "Long fade"),
    )),
    "Music · Calm": (True, (
        ("#7FD3D0", 45, 8_000, "Slow fade"),
        ("#9AB8F0", 40, 8_000, "Slow fade"),
        ("#B9A6E8", 42, 8_000, "Slow fade"),
    )),
    "Music · Cozy": (True, (
        ("#FFB067", 55, 6_000, "Slow fade"),
        ("#FF9A4D", 48, 6_000, "Slow fade"),
        (2700, 58, 6_000, "Slow fade"),
    )),
    "Music · Romantic": (True, (
        ("#FF6F91", 40, 5_000, "Slow fade"),
        ("#FF8A65", 45, 5_000, "Slow fade"),
        ("#E0558B", 36, 5_000, "Slow fade"),
    )),
    "Music · Melancholic": (True, (
        ("#3D5AFE", 30, 8_000, "Slow fade"),
        ("#5C6BC0", 26, 8_000, "Slow fade"),
        ("#4A6FA5", 32, 8_000, "Slow fade"),
    )),
    "Music · Upbeat": (True, (
        ("#FFC145", 85, 1_500, "Smooth"),
        ("#FF7F50", 80, 1_500, "Smooth"),
        ("#FFD166", 90, 1_500, "Smooth"),
        ("#FF9F1C", 85, 1_500, "Smooth"),
    )),
    "Music · Energetic": (True, (
        ("#FF0055", 100, 400, "Quick fade"),
        ("#7A00FF", 100, 400, "Quick fade"),
        ("#00C2FF", 100, 400, "Quick fade"),
        ("#FFB800", 100, 400, "Quick fade"),
    )),
}


class MusicPresets:
    """Names of the built-in music schemes, and how hard each mood pulses on the beats."""

    # 0-1: how far a full-strength beat lifts the brightness. Sleep and focus keep
    # their smooth schemes; the livelier the mood, the harder the lights hit.
    BEAT_DEPTH = {
        "sleep": 0.0, "focus": 0.0, "calm": 0.15, "melancholic": 0.2,
        "romantic": 0.25, "cozy": 0.3, "upbeat": 0.55, "energetic": 0.85,
    }

    @staticmethod
    def name(mood: str) -> str:
        return f"Music · {mood.capitalize()}"

    @staticmethod
    def moods() -> tuple[str, ...]:
        return MUSIC_MOODS


class WeatherPresets:
    """Names of the built-in weather schemes."""

    LABELS = {
        "clear": "Clear", "partly_cloudy": "Partly cloudy", "cloudy": "Cloudy", "fog": "Fog",
        "rain": "Rain", "thunderstorm": "Thunderstorm", "snow": "Snow",
    }

    @classmethod
    def name(cls, condition: str, daypart: str) -> str:
        return f"Weather · {cls.LABELS[condition]} {daypart}"

    @classmethod
    def slots(cls) -> list[tuple[str, str]]:
        return [(condition, daypart) for condition in WEATHER_CONDITIONS for daypart in DAYPARTS]


class PresetCatalog:
    """Install the built-in transitions, then the schemes that reference them.

    With ``weather_slots`` (``music_slots``), each weather slot (music mood) without
    a scheme is pointed at its built-in scheme.
    """

    def __init__(
        self,
        scenes: SceneRepository,
        transitions: TransitionRepository,
        weather_slots: WeatherSchemeRepository | None = None,
        music_slots: MusicSchemeRepository | None = None,
    ) -> None:
        self.scenes = scenes
        self.transitions = transitions
        self.weather_slots = weather_slots
        self.music_slots = music_slots

    @staticmethod
    def light(value: str | int) -> dict[str, Any]:
        return {"color": value} if isinstance(value, str) else {"color_temp": value}

    def install(self) -> None:
        for transition in TRANSITIONS:
            self.transitions.upsert_preset(transition)
        transition_ids = {row["name"]: row["id"] for row in self.transitions.list()}
        for name, value, brightness in SOLIDS + WEATHER_SOLIDS + MUSIC_SOLIDS:
            self.scenes.upsert_preset(
                SceneCreate(name=name, brightness=brightness, **self.light(value))
            )
        for name, (loops, steps) in {**SEQUENCES, **WEATHER_SEQUENCES, **MUSIC_SEQUENCES}.items():
            self.scenes.upsert_preset(
                SceneCreate(
                    name=name,
                    kind="sequence",
                    loops=loops,
                    steps=[
                        SceneStep(
                            brightness=brightness,
                            hold_ms=hold_ms,
                            transition_id=transition_ids.get(transition),
                            **self.light(value),
                        )
                        for value, brightness, hold_ms, transition in steps
                    ],
                )
            )
        if self.weather_slots:
            self.seed_weather_slots()
        if self.music_slots:
            self.seed_music_slots()

    def seed_weather_slots(self) -> None:
        preset_ids = {row["name"]: row["id"] for row in self.scenes.list() if row["is_preset"]}
        for condition, daypart in WeatherPresets.slots():
            scene_id = preset_ids.get(WeatherPresets.name(condition, daypart))
            if scene_id is not None:
                self.weather_slots.seed(condition, daypart, scene_id)

    def seed_music_slots(self) -> None:
        preset_ids = {row["name"]: row["id"] for row in self.scenes.list() if row["is_preset"]}
        for mood in MusicPresets.moods():
            scene_id = preset_ids.get(MusicPresets.name(mood))
            if scene_id is not None:
                self.music_slots.seed(mood, scene_id)
