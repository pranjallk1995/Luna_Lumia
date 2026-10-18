"""Animate sequence schemes on lights: fades between steps, holds, and loops.

WiZ bulbs only accept static states, so a sequence is played by sending
interpolated frames from a dedicated event-loop thread.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

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

    def blend(self, previous: Step, t: float) -> dict[str, Any]:
        """The light state ``t`` (0..1, already eased) of the way from ``previous``."""
        brightness = max(1, round(previous.brightness + (self.brightness - previous.brightness) * t))
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


@dataclass
class Playback:
    scene_id: int
    steps: list[Step]
    loops: bool
    lights: dict[int, str]  # light id -> IP address
    task: asyncio.Task | None = field(default=None, repr=False)


class SceneEngine:
    """Play sequence schemes on a private event loop; one playback per light.

    ``play`` and ``stop`` are thread-safe and may be called from the HTTP server,
    the MCP tools, or the scheduler thread.
    """

    FRAME_SECONDS = 0.12  # ~8 updates per second per light
    SEND_TIMEOUT = 0.35  # an unreachable bulb must not stall the other lights' frames

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
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=5)

    def play(self, scene_id: int, steps: list[Step], loops: bool, lights: list[Row]) -> None:
        targets = {light["id"]: light["ip_address"] for light in lights}
        self._call(self._play(Playback(scene_id, steps, loops, targets)))

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
        playback.task = self.loop.create_task(self._run(playback))

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
                asyncio.gather(*sends, return_exceptions=True), self.SEND_TIMEOUT
            )
        except asyncio.TimeoutError:
            pass

    async def _fade(self, playback: Playback, previous: Step | None, step: Step) -> None:
        if previous is None or step.fade_s <= 0:
            await self._frame(playback, step.state)
            return
        frames = max(1, round(step.fade_s / self.FRAME_SECONDS))
        started = time.monotonic()
        for frame in range(1, frames + 1):
            state = step.state if frame == frames else step.blend(
                previous, ColorMath.ease(step.curve, frame / frames)
            )
            await self._frame(playback, state)
            # Anchor to the start time so slow sends do not stretch the fade.
            await asyncio.sleep(max(0.0, started + step.fade_s * frame / frames - time.monotonic()))

    async def _run(self, playback: Playback) -> None:
        previous, index = None, 0
        try:
            while playback.lights:
                step = playback.steps[index]
                await self._fade(playback, previous, step)
                # A zero-length step still yields so a looping sequence cannot spin.
                await asyncio.sleep(max(step.hold_s, 0 if step.fade_s else self.FRAME_SECONDS))
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
