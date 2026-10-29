"""Animate sequence schemes on lights: fades between steps, holds, and loops.

WiZ bulbs only accept static states, so a sequence is played by sending
interpolated frames from a dedicated event-loop thread. The same thread plays
beat pulses: frames computed from where a track is, by the clock, so they
follow the music without drifting.
"""

from __future__ import annotations

import asyncio
import bisect
import math
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import AppConfig

Row = dict[str, Any]
Sender = Callable[..., Awaitable[None]]


class ColorMath:
    """Color conversions and easing curves for interpolating light states."""

    CURVES: dict[str, Callable[[float], float]] = {
        "linear": lambda t: t,
        "ease-in": lambda t: t * t,
        "ease-out": lambda t: 1 - (1 - t) ** 2,
        "ease-in-out": lambda t: t * t * (3 - 2 * t),
    }

    @staticmethod
    def hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    @staticmethod
    def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
        return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))

    @staticmethod
    def kelvin_to_rgb(kelvin: int) -> tuple[int, int, int]:
        """Approximate a white temperature as RGB (Tanner Helland's fit)."""
        t = kelvin / 100
        red = 255 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
        green = (
            99.4708025861 * math.log(t) - 161.1195681661
            if t <= 66
            else 288.1221695283 * (t - 60) ** -0.0755148492
        )
        blue = 255 if t >= 66 else 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
        return tuple(max(0, min(255, round(c))) for c in (red, green, blue))

    @classmethod
    def preview_hex(cls, color: str | None, color_temp: int | None) -> str:
        return color.upper() if color else cls.rgb_to_hex(cls.kelvin_to_rgb(color_temp))

    @classmethod
    def ease(cls, curve: str, t: float) -> float:
        return cls.CURVES.get(curve, cls.CURVES["linear"])(max(0.0, min(1.0, t)))


@dataclass(frozen=True)
class Step:
    """A sequence step resolved with its incoming transition."""

    color: str | None
    color_temp: int | None
    brightness: int
    hold_s: float
    fade_s: float
    curve: str

    @property
    def rgb(self) -> tuple[int, int, int]:
        if self.color:
            return ColorMath.hex_to_rgb(self.color)
        return ColorMath.kelvin_to_rgb(self.color_temp)

    @classmethod
    def from_scene(cls, scene: Row, transitions: dict[int, Row]) -> list[Step]:
        """Resolve stored steps; an unknown transition plays as an instant change."""
        steps = []
        for raw in scene["steps"]:
            transition = transitions.get(raw.get("transition_id")) or {}
            steps.append(
                cls(
                    color=raw.get("color"),
                    color_temp=raw.get("color_temp"),
                    brightness=int(raw["brightness"]),
                    hold_s=raw.get("hold_ms", 0) / 1000,
                    fade_s=transition.get("duration_ms", 0) / 1000,
                    curve=transition.get("curve", "linear"),
                )
            )
        return steps

    @property
    def is_black(self) -> bool:
        """Black means "off" (WiZ cannot show it)."""
        return bool(self.color) and self.color.upper() == "#000000"

    def blend(self, previous: Step, t: float) -> dict[str, Any]:
        """The light state ``t`` (0..1, already eased) of the way from ``previous``."""
        brightness = max(1, round(previous.brightness + (self.brightness - previous.brightness) * t))
        if previous.is_black or self.is_black:
            # Fading to/from black dims the lit color at full strength. Scaling its
            # RGB toward 0 instead gives very dark values that WiZ bulbs render as
            # orange or warm white rather than a dim version of the color.
            lit = previous if self.is_black else self
            if lit.is_black:
                return self.state
            return {**lit.state, "brightness": brightness}
        if previous.color_temp and self.color_temp:
            kelvin = round(previous.color_temp + (self.color_temp - previous.color_temp) * t)
            return {"brightness": brightness, "color_temp": kelvin}
        start, end = previous.rgb, self.rgb
        rgb = tuple(a + (b - a) * t for a, b in zip(start, end))
        return {"brightness": brightness, "color": ColorMath.rgb_to_hex(rgb)}

    @property
    def state(self) -> dict[str, Any]:
        if self.color:
            return {"brightness": self.brightness, "color": self.color}
        return {"brightness": self.brightness, "color_temp": self.color_temp}


@dataclass(frozen=True)
class BeatClock:
    """Where a playing track is, and the light state for that moment.

    Each beat (or every other one, when they come faster than ``MIN_BEAT_S``,
    which usually means the tempo was read double) lifts the brightness by up to
    ``depth`` of the way to full, scaled by how strongly the beat hits, and lets it
    fall away before the next. The palette (a scheme's steps) moves on every bar
    of four beats, crossfading quickly for lively music and slowly for calm.
    """

    MIN_BEAT_S = 0.4
    BAR = 4

    beats: tuple[float, ...]
    strengths: tuple[float, ...]
    started_at: float  # Unix time of the track's second 0
    offset_s: float  # how much later the sound is heard
    depth: float  # 0-1: how far a full-strength beat lifts the brightness
    duration_s: float

    def position(self, now: float | None = None) -> float:
        return (time.time() if now is None else now) - self.started_at - self.offset_s

    def pulse_beats(self) -> tuple[int, ...]:
        if len(self.beats) < 2:
            return tuple(range(len(self.beats)))
        intervals = sorted(b - a for a, b in zip(self.beats, self.beats[1:]))
        step = 2 if intervals[len(intervals) // 2] < self.MIN_BEAT_S else 1
        return tuple(range(0, len(self.beats), step))

    def state(self, palette: list[Step], position: float, pulses: tuple[int, ...]) -> dict[str, Any]:
        times = [self.beats[i] for i in pulses]
        index = bisect.bisect_right(times, position) - 1
        bar = max(index, 0) // self.BAR
        color = palette[bar % len(palette)]
        if index >= 0 and len(palette) > 1:
            bar_start = times[bar * self.BAR]
            fade_s = 0.15 if self.depth > 0.6 else 1.5
            mix = min(1.0, (position - bar_start) / fade_s)
            state = color.blend(palette[(bar - 1) % len(palette)], ColorMath.ease("ease-in-out", mix))
        else:
            state = dict(color.state)
        base = state["brightness"]
        low = base * (1 - 0.5 * self.depth)
        lift = 0.0
        if index >= 0 and position <= self.duration_s:
            beat = pulses[index]
            following = times[index + 1] if index + 1 < len(times) else times[index] + 0.5
            decay_s = max(0.08, 0.35 * (following - times[index]))
            strength = self.strengths[beat] if beat < len(self.strengths) else 0.5
            lift = self.depth * (0.4 + 0.6 * strength) * math.exp(-(position - times[index]) / decay_s)
        state["brightness"] = max(1, min(100, round(low + (100 - low) * lift)))
        return state

    def next_wait(self, position: float, pulses: tuple[int, ...]) -> float:
        """Sleep a frame, or less to land exactly on the next pulse."""
        times = [self.beats[i] for i in pulses]
        index = bisect.bisect_right(times, position)
        until_beat = times[index] - position if index < len(times) else math.inf
        return max(0.005, min(AppConfig.PLAYBACK_FRAME_SECONDS, until_beat))


@dataclass
class Playback:
    scene_id: int
    steps: list[Step]
    loops: bool
    lights: dict[int, str]  # light id -> IP address
    task: asyncio.Task | None = field(default=None, repr=False)
    clock: BeatClock | None = None


class SceneEngine:
    """Play sequence schemes on a private event loop; one playback per light.

    ``play`` and ``stop`` are thread-safe and may be called from the HTTP server,
    the MCP tools, or the scheduler thread.
    """

    def __init__(self, send: Sender) -> None:
        self.send = send
        self.loop = asyncio.new_event_loop()
        self.playbacks: dict[int, Playback] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self.loop.run_forever, daemon=True, name="lumia-scene-engine"
        )
        self._thread.start()

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)

    def _call(self, coroutine: Awaitable[Any]) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=AppConfig.PLAYBACK_CALL_TIMEOUT_SECONDS)

    def play(self, scene_id: int, steps: list[Step], loops: bool, lights: list[Row]) -> None:
        targets = {light["id"]: light["ip_address"] for light in lights}
        self._call(self._play(Playback(scene_id, steps, loops, targets)))

    def play_beats(self, scene_id: int, palette: list[Step], clock: BeatClock, lights: list[Row]) -> None:
        """Pulse ``lights`` on the beats of a playing track, in the palette's colors."""
        targets = {light["id"]: light["ip_address"] for light in lights}
        self._call(self._play(Playback(scene_id, palette, True, targets, clock=clock)))

    def beats_playing(self) -> bool:
        with self._lock:
            return any(playback.clock is not None for playback in self.playbacks.values())

    def stop(self, light_ids: list[int]) -> None:
        if light_ids:
            self._call(self._stop(light_ids))

    def playing(self) -> dict[int, int]:
        """Light id -> id of the scheme currently playing on it."""
        with self._lock:
            return {light_id: playback.scene_id for light_id, playback in self.playbacks.items()}

    async def _play(self, playback: Playback) -> None:
        await self._stop(list(playback.lights))
        with self._lock:
            for light_id in playback.lights:
                self.playbacks[light_id] = playback
        runner = self._run_beats if playback.clock else self._run
        playback.task = self.loop.create_task(runner(playback))

    async def _stop(self, light_ids: list[int]) -> None:
        with self._lock:
            for light_id in light_ids:
                playback = self.playbacks.pop(light_id, None)
                if playback is None:
                    continue
                playback.lights.pop(light_id, None)
                if not playback.lights and playback.task:
                    playback.task.cancel()

    async def _frame(self, playback: Playback, state: dict[str, Any]) -> None:
        sends = [self.send(ip, **state) for ip in list(playback.lights.values())]
        try:
            await asyncio.wait_for(
                asyncio.gather(*sends, return_exceptions=True), AppConfig.PLAYBACK_SEND_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            pass

    async def _fade(self, playback: Playback, previous: Step | None, step: Step) -> None:
        if previous is None or step.fade_s <= 0:
            await self._frame(playback, step.state)
            return
        frames = max(1, round(step.fade_s / AppConfig.PLAYBACK_FRAME_SECONDS))
        started = time.monotonic()
        for frame in range(1, frames + 1):
            state = step.state if frame == frames else step.blend(
                previous, ColorMath.ease(step.curve, frame / frames)
            )
            await self._frame(playback, state)
            # Anchor to the start time so slow sends do not stretch the fade.
            await asyncio.sleep(max(0.0, started + step.fade_s * frame / frames - time.monotonic()))

    async def _run_beats(self, playback: Playback) -> None:
        """Send each light the state for the track's position, each light on its own.

        Bulbs answer in a few milliseconds but now and then stall for hundreds; a
        light whose last frame has not been answered skips frames instead of
        holding the others back or falling behind the music.
        """
        clock, palette = playback.clock, playback.steps
        pulses = clock.pulse_beats()
        sending: dict[str, asyncio.Task] = {}
        sent: dict[str, dict[str, Any]] = {}
        try:
            while playback.lights:
                position = clock.position()
                state = clock.state(palette, position, pulses)
                for ip in list(playback.lights.values()):
                    busy = sending.get(ip)
                    if (busy and not busy.done()) or sent.get(ip) == state:
                        continue
                    sent[ip] = state
                    sending[ip] = self.loop.create_task(
                        asyncio.wait_for(self.send(ip, **state), AppConfig.PLAYBACK_SEND_TIMEOUT_SECONDS)
                    )
                    sending[ip].add_done_callback(lambda task: task.cancelled() or task.exception())
                await asyncio.sleep(clock.next_wait(position, pulses))
        finally:
            for task in sending.values():
                task.cancel()
            with self._lock:
                for light_id in list(playback.lights):
                    if self.playbacks.get(light_id) is playback:
                        del self.playbacks[light_id]

    async def _run(self, playback: Playback) -> None:
        previous, index = None, 0
        try:
            while playback.lights:
                step = playback.steps[index]
                await self._fade(playback, previous, step)
                # A zero-length step still yields so a looping sequence cannot spin.
                await asyncio.sleep(max(step.hold_s, 0 if step.fade_s else AppConfig.PLAYBACK_FRAME_SECONDS))
                previous, index = step, index + 1
                if index == len(playback.steps):
                    if not playback.loops:
                        break
                    index = 0
        finally:
            with self._lock:
                for light_id in list(playback.lights):
                    if self.playbacks.get(light_id) is playback:
                        del self.playbacks[light_id]
