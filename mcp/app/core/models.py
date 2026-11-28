"""Validated request and command models for Luna Lumia."""

import re
from datetime import date, time
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CollectionKind = Literal["room", "group"]
ScheduleTarget = Literal["all", "light", "group"]
HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class Validators:
    """Reusable normalization rules shared by several models."""

    @staticmethod
    def image_url(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("Image URL must use http or https")
        return cleaned

    @staticmethod
    def entity_name(value: str, entity: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{entity} name cannot be blank")
        if not all(character.isalnum() or character == " " for character in cleaned):
            raise ValueError(
                f"{entity} name may contain only letters, numbers, and spaces"
            )
        return cleaned

    @staticmethod
    def mac_address(value: str | None) -> str | None:
        if value is None:
            return None
        compact = value.replace(":", "").replace("-", "").strip().upper()
        if len(compact) != 12 or any(
            character not in "0123456789ABCDEF" for character in compact
        ):
            raise ValueError("Invalid MAC address")
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


class LightNamed(BaseModel):
    """Base for payloads carrying a validated light name."""

    name: str = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return Validators.entity_name(value, "Light")


class CollectionNamed(BaseModel):
    """Base for payloads carrying a validated room or group name."""

    name: str = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return Validators.entity_name(value, "Room/group")


class LightCreate(LightNamed):
    ip_address: str = Field(pattern=r"^(?:\d{1,3}\.){3}\d{1,3}$")
    protocol: Literal["wiz", "openrgb", "icue"] = "wiz"
    mac_address: str | None = Field(default=None, max_length=17)
    # PC devices only: the device's name as OpenRGB or iCUE lists it (e.g. "ASUS B860M MAX GAMING AX").
    device: str | None = Field(default=None, min_length=1, max_length=100)
    # PC devices only: the port OpenRGB or the iCUE bridge listens on, when not its default.
    port: int | None = Field(default=None, ge=1, le=65535)
    # OpenRGB only: a part of the device as its own light. zone is a zone's name or its
    # number from 1 (an ARGB header); leds a range such as "2-25" within it (or within the device).
    zone: str | None = Field(default=None, min_length=1, max_length=100)
    leds: str | None = Field(default=None, pattern=r"^\d{1,4}(-\d{1,4})?$")

    @model_validator(mode="after")
    def device_matches_protocol(self):
        if (self.protocol != "wiz") != (self.device is not None):
            raise ValueError("PC lights need a device name; WiZ lights take none")
        if self.protocol == "wiz" and self.port is not None:
            raise ValueError("WiZ lights take no port")
        if self.protocol != "openrgb" and (self.zone or self.leds):
            raise ValueError("Only OpenRGB devices can be split into zones and LED ranges")
        if self.leds and "-" in self.leds:
            first, last = (int(part) for part in self.leds.split("-"))
            if not 1 <= first <= last:
                raise ValueError("An LED range counts from 1 and runs low to high, such as 2-25")
        return self

    @field_validator("ip_address")
    @classmethod
    def valid_octets(cls, value: str) -> str:
        if any(int(part) > 255 for part in value.split(".")):
            raise ValueError("Invalid IPv4 address")
        return value

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, value: str | None) -> str | None:
        return Validators.mac_address(value)


class LightUpdate(LightNamed):
    pass


class LightState(BaseModel):
    """A partial light state; a bulb shows either an RGB color or a white temperature."""

    MIN_COLOR_TEMP: ClassVar[int] = 2200
    MAX_COLOR_TEMP: ClassVar[int] = 6500

    on: bool | None = None
    brightness: int | None = Field(default=None, ge=1, le=100)
    color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    color_temp: int | None = Field(default=None, ge=MIN_COLOR_TEMP, le=MAX_COLOR_TEMP)

    @model_validator(mode="after")
    def one_color_mode(self):
        if self.color is not None and self.color_temp is not None:
            raise ValueError("Set either color or color_temp, not both")
        return self

    @model_validator(mode="after")
    def black_means_off(self):
        """WiZ bulbs cannot show black (RGB 0,0,0 falls back to warm white), so black turns the light off."""
        if self.color is not None and self.color.upper() == "#000000":
            self.color, self.on = None, False
        return self


class LightImageUpdate(BaseModel):
    image_url: str | None = Field(default=None, max_length=2048)

    @field_validator("image_url")
    @classmethod
    def valid_image_url(cls, value: str | None) -> str | None:
        return Validators.image_url(value)


class RoomImageUpdate(BaseModel):
    room_key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    image_url: str = Field(min_length=1, max_length=2048)

    @field_validator("image_url")
    @classmethod
    def valid_image_url(cls, value: str) -> str:
        return Validators.image_url(value)  # type: ignore[return-value]


class GroupCreate(CollectionNamed):
    light_ids: list[int] = Field(min_length=1)


class GroupUpdate(CollectionNamed):
    pass


class GroupMembersUpdate(BaseModel):
    light_ids: list[int] = Field(min_length=1)


TransitionCurve = Literal["linear", "ease-in", "ease-out", "ease-in-out"]


class TransitionCreate(BaseModel):
    """A reusable fade from one scheme step to the next."""

    name: str = Field(min_length=1, max_length=60)
    duration_ms: int = Field(ge=0, le=600_000)
    curve: TransitionCurve = "ease-in-out"


class LightColor(BaseModel):
    """Exactly one of an RGB color or a white temperature, at a brightness."""

    color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    color_temp: int | None = Field(
        default=None, ge=LightState.MIN_COLOR_TEMP, le=LightState.MAX_COLOR_TEMP
    )

    @model_validator(mode="after")
    def one_color_mode(self):
        if (self.color is None) == (self.color_temp is None):
            raise ValueError("Set exactly one of color or color_temp")
        if self.color:
            self.color = self.color.upper()
        return self


# A keyboard key or LED group as the iCUE bridge names it ("W", "Space", "Keypad7", "Mouse 1"),
# or a group of keys such as "wasd" or "arrows".
KEY_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _]{0,39}")
HEX_COLOR = re.compile(HEX_COLOR_PATTERN)


class Effect(BaseModel):
    """Motion on top of a step while it holds: keys (or the whole light) blink, strobe, breathe, glow, or cycle colors.

    blink: ``color`` half of each period, ``to`` the other half. strobe: a short flash of ``color``, then ``to``.
    breathe: a smooth swell between ``color`` and ``to``. glow: a gentle swell, ``color`` never dimming below a third.
    rainbow: every hue in turn, once a period. ``color`` defaults to what the step gives those keys, ``to`` to black
    (off). ``keys`` names keys, LEDs, or groups (built-in or your shortcut keys); none means the whole light.
    ``stagger_ms`` starts each listed key that much later than the one before, so a row of keys chases or waves.
    """

    MAX_EFFECTS: ClassVar[int] = 8

    type: Literal["blink", "strobe", "breathe", "glow", "rainbow"]
    keys: list[str] | None = None
    color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    to: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    period_ms: int = Field(default=1_000, ge=200, le=60_000)
    stagger_ms: int = Field(default=0, ge=0, le=10_000)

    @field_validator("keys")
    @classmethod
    def valid_keys(cls, keys: list[str] | None) -> list[str] | None:
        if keys is None:
            return None
        if not keys or len(keys) > SceneStep.MAX_KEYS:
            raise ValueError(f"An effect names 1 to {SceneStep.MAX_KEYS} keys, or none for the whole light")
        for name in keys:
            if not KEY_NAME_PATTERN.fullmatch(name.strip()):
                raise ValueError(f"{name!r} is not a key name; see list_light_leds")
        return [name.strip() for name in keys]

    @model_validator(mode="after")
    def upper_colors(self):
        self.color = self.color.upper() if self.color else None
        self.to = self.to.upper() if self.to else None
        return self


class SceneStep(LightColor):
    """One step of a sequence: fade in with ``transition_id``, then hold.

    In a per-key scheme ``keys`` colors keyboard keys by name; ``color`` (or
    ``color_temp``) is every other key, and all of a light without per-key colors.
    """

    MAX_KEYS: ClassVar[int] = 200

    brightness: int = Field(ge=1, le=100)
    hold_ms: int = Field(default=1_000, ge=0, le=3_600_000)
    transition_id: int | None = None
    keys: dict[str, str] | None = None
    # Played while the step holds; a step with effects and no hold plays them until stopped.
    effects: list[Effect] | None = None

    @field_validator("effects")
    @classmethod
    def few_effects(cls, effects: list[Effect] | None) -> list[Effect] | None:
        if effects is not None and len(effects) > Effect.MAX_EFFECTS:
            raise ValueError(f"A step has at most {Effect.MAX_EFFECTS} effects")
        return effects or None

    @field_validator("keys")
    @classmethod
    def valid_keys(cls, keys: dict[str, str] | None) -> dict[str, str] | None:
        if keys is None:
            return None
        if len(keys) > cls.MAX_KEYS:
            raise ValueError(f"A step colors at most {cls.MAX_KEYS} keys")
        cleaned = {}
        for name, color in keys.items():
            if not KEY_NAME_PATTERN.fullmatch(name.strip()):
                raise ValueError(f"{name!r} is not a key name; see list_light_leds")
            if not isinstance(color, str) or not HEX_COLOR.fullmatch(color):
                raise ValueError(f"The color of {name!r} must be #RRGGBB")
            cleaned[name.strip()] = color.upper()
        return cleaned


class LedPaint(BaseModel):
    """Colors for a PC light's keys or LEDs now: each named one its own, the rest ``color``."""

    color: str = Field(default="#000000", pattern=HEX_COLOR_PATTERN)
    brightness: int = Field(default=100, ge=1, le=100)
    keys: dict[str, str] | None = None

    @field_validator("keys")
    @classmethod
    def valid_keys(cls, keys: dict[str, str] | None) -> dict[str, str] | None:
        return SceneStep.valid_keys(keys)


class SceneCreate(BaseModel):
    """A solid scheme (one color or temperature) or a sequence of steps.

    The original ``{name, color, brightness}`` shape is still a valid solid scheme.
    """

    MAX_STEPS: ClassVar[int] = 24

    name: str = Field(min_length=1, max_length=100)
    kind: Literal["solid", "sequence", "keys"] = "solid"
    color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    color_temp: int | None = Field(
        default=None, ge=LightState.MIN_COLOR_TEMP, le=LightState.MAX_COLOR_TEMP
    )
    brightness: int | None = Field(default=None, ge=1, le=100)
    steps: list[SceneStep] = Field(default_factory=list)
    loops: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Scheme name cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def valid_kind(self):
        if self.kind == "solid":
            if (self.color is None) == (self.color_temp is None):
                raise ValueError("A solid scheme needs exactly one of color or color_temp")
            if self.brightness is None:
                raise ValueError("A solid scheme needs a brightness")
            if self.steps:
                raise ValueError("A solid scheme has no steps")
            self.color = self.color.upper() if self.color else None
        elif self.kind == "keys":
            if not 1 <= len(self.steps) <= self.MAX_STEPS:
                raise ValueError(f"A per-key scheme needs 1 to {self.MAX_STEPS} steps")
            if not any(step.keys or any(effect.keys for effect in step.effects or []) for step in self.steps):
                raise ValueError("A per-key scheme colors or animates keys in at least one step")
            self.color = self.color_temp = self.brightness = None
        else:
            # One step is enough when it moves: an effect such as a blink or a glow.
            fewest = 1 if any(step.effects for step in self.steps) else 2
            if not fewest <= len(self.steps) <= self.MAX_STEPS:
                raise ValueError(f"A sequence needs {fewest} to {self.MAX_STEPS} steps"
                                 + ("" if fewest == 1 else ", or one with an effect"))
            if any(step.keys or any(effect.keys for effect in step.effects or []) for step in self.steps):
                raise ValueError("Colors or effects per key need a per-key scheme (kind \"keys\")")
            self.color = self.color_temp = self.brightness = None
        return self


class KeyGroupCreate(BaseModel):
    """Your own named set of keys ("Copy" = LeftCtrl and C), used like the built-in groups wasd or arrows."""

    MAX_KEYS: ClassVar[int] = 120

    name: str = Field(min_length=1, max_length=40)
    keys: list[str] = Field(min_length=1)
    color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)  # how it is shown, if painted

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not KEY_NAME_PATTERN.fullmatch(cleaned):
            raise ValueError("A shortcut's name may use letters, numbers, spaces, and _ (up to 40)")
        return cleaned

    @field_validator("keys")
    @classmethod
    def valid_keys(cls, keys: list[str]) -> list[str]:
        if len(keys) > cls.MAX_KEYS:
            raise ValueError(f"A shortcut has at most {cls.MAX_KEYS} keys")
        cleaned = []
        for name in keys:
            if not KEY_NAME_PATTERN.fullmatch(name.strip()):
                raise ValueError(f"{name!r} is not a key name; see list_light_leds")
            if name.strip() not in cleaned:
                cleaned.append(name.strip())
        return cleaned

    @model_validator(mode="after")
    def upper_color(self):
        self.color = self.color.upper() if self.color else None
        return self


# What a hotkey's last key may be, as Windows names it to RegisterHotKey.
HOTKEY_MODIFIERS = ("Ctrl", "Alt", "Shift", "Win")
HOTKEY_KEYS = (
    *"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", *(f"F{n}" for n in range(1, 25)), *(f"Num{n}" for n in range(10)),
    "Space", "Enter", "Tab", "Escape", "Backspace", "Insert", "Delete", "Home", "End", "PageUp", "PageDown",
    "Up", "Down", "Left", "Right", "PrintScreen", "Pause", "NumMultiply", "NumAdd", "NumSubtract", "NumDivide",
    "NumDecimal", "VolumeUp", "VolumeDown", "VolumeMute", "MediaPlayPause", "MediaNext", "MediaPrevious", "MediaStop",
)
_HOTKEY_ALIASES = {"control": "Ctrl", "ctl": "Ctrl", "option": "Alt", "windows": "Win", "super": "Win", "meta": "Win",
                   "cmd": "Win", "esc": "Escape", "return": "Enter", "del": "Delete", "ins": "Insert",
                   "pgup": "PageUp", "pgdn": "PageDown", "arrowup": "Up", "arrowdown": "Down", "arrowleft": "Left",
                   "arrowright": "Right", "uparrow": "Up", "downarrow": "Down", "leftarrow": "Left",
                   "rightarrow": "Right", "spacebar": "Space", "prtsc": "PrintScreen"}


def normalize_hotkey(combo: str) -> str:
    """"ctrl + alt + 1" -> "Ctrl+Alt+1": at least one modifier, in a fixed order, and one key."""
    names = {name.casefold(): name for name in (*HOTKEY_MODIFIERS, *HOTKEY_KEYS)}
    parts = [part.strip() for part in combo.replace(" ", "").split("+") if part.strip()]
    resolved = [_HOTKEY_ALIASES.get(part.casefold()) or names.get(part.casefold()) for part in parts]
    if not parts or None in resolved:
        bad = [part for part, name in zip(parts, resolved) if name is None]
        raise ValueError(f"Unknown key {bad[0] if bad else combo!r} in the hotkey; keys: {', '.join(HOTKEY_KEYS)}")
    modifiers = [name for name in HOTKEY_MODIFIERS if name in resolved]
    keys = [name for name in resolved if name not in HOTKEY_MODIFIERS]
    if len(keys) != 1:
        raise ValueError("A hotkey is modifiers (Ctrl, Alt, Shift, Win) and one other key, such as Ctrl+Alt+1")
    stands_alone = re.fullmatch(r"F\d{1,2}", keys[0]) or keys[0].startswith(("Media", "Volume"))
    if not modifiers and not stands_alone:
        raise ValueError("A hotkey needs Ctrl, Alt, Shift, or Win, unless its key is F1-F24 or a media key")
    if modifiers == ["Shift"] and len(keys[0]) == 1:
        raise ValueError("Shift with a letter or digit is typing; add Ctrl, Alt, or Win")
    return "+".join([*modifiers, keys[0]])


class HotkeyCreate(BaseModel):
    """A key combination on the PC that plays a scheme on a target, stops what plays there, turns lights off,
    or opens an app on that PC (one the bridge lists, by name: see list_shortcuts).

    Pressed anywhere on the PC that runs the iCUE bridge (Windows hands the combination to Lumia
    instead of the app in front, so pick one no app needs). The keyboard's Fn key never reaches Windows.
    """

    combo: str
    action: Literal["scene", "stop", "off", "open"] = "scene"
    scene_id: int | None = None
    app: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    target_type: Literal["all", "on", "light", "group"] = "all"  # rooms are groups too
    target_id: int | None = None
    enabled: bool = True

    @field_validator("combo")
    @classmethod
    def valid_combo(cls, value: str) -> str:
        return normalize_hotkey(value)

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "scene" and self.scene_id is None:
            raise ValueError("Choose the scheme the hotkey plays")
        if self.action != "scene":
            self.scene_id = None
        if self.action == "open" and not self.app:
            raise ValueError("Choose the app the hotkey opens")
        if self.action != "open":
            self.app = None
        else:
            self.target_type, self.target_id = "all", None
        if self.target_type in ("all", "on"):
            self.target_id = None
        elif self.target_id is None:
            raise ValueError("A light or group (room) target needs its id")
        return self


class LocationUpdate(BaseModel):
    """Where sunrise and sunset are calculated for."""

    name: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Location name cannot be blank")
        return cleaned


class ScheduleCreate(BaseModel):
    """A schedule: at ``run_time``, or at sunrise/sunset plus ``offset_minutes``.

    It repeats on ``weekdays``, or runs once on ``run_date`` when one is given.
    """

    name: str = Field(min_length=1, max_length=100)
    kind: Literal["schedule", "alarm"] = "schedule"
    target_type: ScheduleTarget = "all"
    target_id: int | None = None
    action: Literal["on", "off", "scene"]
    scene_id: int | None = None
    time_mode: Literal["time", "sunrise", "sunset"] = "time"
    run_time: time | None = None
    offset_minutes: int = Field(default=0, ge=-180, le=180)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    run_date: date | None = None
    enabled: bool = True

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        if not value or any(day < 0 or day > 6 for day in value):
            raise ValueError("Choose at least one valid weekday")
        return sorted(set(value))

    @model_validator(mode="after")
    def valid_target_and_action(self):
        if self.target_type != "all" and self.target_id is None:
            raise ValueError("A light or group target is required")
        if self.target_type == "all":
            self.target_id = None
        if self.action == "scene" and self.scene_id is None:
            raise ValueError("A color scheme is required")
        if self.action != "scene":
            self.scene_id = None
        if self.time_mode == "time":
            if self.run_time is None:
                raise ValueError("Choose a time")
            self.offset_minutes = 0
        else:
            self.run_time = None
        if self.run_date is not None:
            self.weekdays = [self.run_date.weekday()]
        return self


WeatherCondition = Literal[
    "clear", "partly_cloudy", "cloudy", "fog", "rain", "thunderstorm", "snow"
]
Daypart = Literal["day", "night"]
WEATHER_CONDITIONS: tuple[str, ...] = WeatherCondition.__args__
DAYPARTS: tuple[str, ...] = Daypart.__args__


class WeatherPeriod(BaseModel):
    """Weather from ``start`` until the next period starts (the first also covers earlier)."""

    # Common forecast words mapped onto the conditions Lumia has schemes for.
    ALIASES: ClassVar[dict[str, str]] = {
        "sunny": "clear", "fair": "clear", "mostly_clear": "clear", "mostly_sunny": "partly_cloudy",
        "partly_sunny": "partly_cloudy", "scattered_clouds": "partly_cloudy",
        "mostly_cloudy": "cloudy", "overcast": "cloudy", "clouds": "cloudy",
        "mist": "fog", "haze": "fog", "smoke": "fog", "dust": "fog", "foggy": "fog",
        "drizzle": "rain", "showers": "rain", "light_rain": "rain", "heavy_rain": "rain", "rainy": "rain",
        "storm": "thunderstorm", "thunder": "thunderstorm", "thunderstorms": "thunderstorm",
        "sleet": "snow", "hail": "snow", "snowy": "snow", "blizzard": "snow",
    }

    start: time
    condition: WeatherCondition
    temperature_c: float | None = Field(default=None, ge=-90, le=60)
    precipitation_chance: int | None = Field(default=None, ge=0, le=100)
    cloud_cover: int | None = Field(default=None, ge=0, le=100)
    humidity: int | None = Field(default=None, ge=0, le=100)
    wind_kph: float | None = Field(default=None, ge=0, le=500)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("condition", mode="before")
    @classmethod
    def normalize_condition(cls, value):
        return cls.condition_key(value)

    @classmethod
    def condition_key(cls, value):
        if not isinstance(value, str):
            return value
        key = value.strip().lower().replace(" ", "_").replace("-", "_")
        return cls.ALIASES.get(key, key)

    @field_validator("start")
    @classmethod
    def whole_minutes(cls, value: time) -> time:
        return value.replace(second=0, microsecond=0, tzinfo=None)


class WeatherReport(BaseModel):
    """One day's weather, as periods through the day."""

    MAX_PERIODS: ClassVar[int] = 48

    day: date
    periods: list[WeatherPeriod] = Field(min_length=1)
    location: str | None = Field(default=None, max_length=80)
    summary: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def ordered_periods(self):
        if len(self.periods) > self.MAX_PERIODS:
            raise ValueError(f"A day has at most {self.MAX_PERIODS} weather periods")
        self.periods.sort(key=lambda period: period.start)
        starts = [period.start for period in self.periods]
        if len(set(starts)) != len(starts):
            raise ValueError("Each weather period needs a different start time")
        return self


class WeatherSlot(BaseModel):
    """A weather condition by day or by night, which has one scheme."""

    condition: WeatherCondition
    daypart: Daypart

    @field_validator("condition", mode="before")
    @classmethod
    def normalize_condition(cls, value):
        return WeatherPeriod.condition_key(value)


class WeatherAutomationUpdate(BaseModel):
    """Whether Lumia follows the weather, and on which lights."""

    enabled: bool
    target_type: Literal["on", "all", "light", "group"] = "on"
    target_id: int | None = None

    @model_validator(mode="after")
    def valid_target(self):
        if self.target_type in ("light", "group") and self.target_id is None:
            raise ValueError("A light or group target is required")
        if self.target_type in ("on", "all"):
            self.target_id = None
        return self


MusicMood = Literal[
    "sleep", "calm", "focus", "cozy", "romantic", "melancholic", "upbeat", "energetic"
]
MUSIC_MOODS: tuple[str, ...] = MusicMood.__args__


class MusicSlot(BaseModel):
    """A music mood, which has one scheme."""

    mood: MusicMood

    @field_validator("mood", mode="before")
    @classmethod
    def normalize_mood(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class MusicAutomationUpdate(WeatherAutomationUpdate):
    """Whether Lumia follows the music Luna Vibia plays, and on which lights."""


class MusicBeatsUpdate(BaseModel):
    """Whether the lights pulse on the beats, and how; None keeps a setting as it is."""

    enabled: bool
    # How much later than Vibia's clock the sound is heard (Bluetooth speakers lag).
    offset_ms: int | None = Field(default=None, ge=-1_000, le=3_000)
    # Scales every mood's pulse depth: 0 is no pulses, 2 twice as strong.
    strength: float | None = Field(default=None, ge=0, le=2)
