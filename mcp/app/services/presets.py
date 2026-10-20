"""Built-in transitions and schemes, installed (or refreshed) at startup."""

from __future__ import annotations

from typing import Any

from app.core.models import SceneCreate, SceneStep, TransitionCreate
from app.data.repositories import SceneRepository, TransitionRepository

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


class PresetCatalog:
    """Install the built-in transitions, then the schemes that reference them."""

    def __init__(self, scenes: SceneRepository, transitions: TransitionRepository) -> None:
        self.scenes = scenes
        self.transitions = transitions

    @staticmethod
    def light(value: str | int) -> dict[str, Any]:
        return {"color": value} if isinstance(value, str) else {"color_temp": value}

    def install(self) -> None:
        for transition in TRANSITIONS:
            self.transitions.upsert_preset(transition)
        transition_ids = {row["name"]: row["id"] for row in self.transitions.list()}
        for name, value, brightness in SOLIDS:
            self.scenes.upsert_preset(
                SceneCreate(name=name, brightness=brightness, **self.light(value))
            )
        for name, (loops, steps) in SEQUENCES.items():
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
