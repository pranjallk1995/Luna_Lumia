import asyncio
import time
import unittest

from pydantic import ValidationError

from app.models import SceneCreate, SceneStep
from app.playback import ColorMath, SceneEngine, Step
from app.presets import SEQUENCES, SOLIDS, TRANSITIONS, PresetCatalog
from app.services import SceneService, TransitionService


def step(brightness=50, hold_s=0.0, fade_s=0.0, curve="linear", **light):
    return Step(light.get("color"), light.get("color_temp"), brightness, hold_s, fade_s, curve)


class ColorMathTests(unittest.TestCase):
    def test_warm_whites_are_red_heavy_and_daylight_is_neutral(self):
        red, green, blue = ColorMath.kelvin_to_rgb(2200)
        self.assertEqual(red, 255)
        self.assertLess(blue, green)
        self.assertGreater(min(ColorMath.kelvin_to_rgb(6500)), 240)

    def test_curves_start_and_end_on_their_endpoints(self):
        for curve in ColorMath.CURVES:
            self.assertEqual(ColorMath.ease(curve, 0), 0)
            self.assertEqual(ColorMath.ease(curve, 1), 1)
        self.assertLess(ColorMath.ease("ease-in", 0.5), 0.5)


class SchemeModelTests(unittest.TestCase):
    def test_original_solid_color_shape_is_still_valid(self):
        scene = SceneCreate(name="Sunset", color="#ff8a5b", brightness=70)
        self.assertEqual((scene.kind, scene.color), ("solid", "#FF8A5B"))

    def test_solid_needs_exactly_one_color_mode(self):
        with self.assertRaises(ValidationError):
            SceneCreate(name="Both", color="#FFFFFF", color_temp=3000, brightness=50)
        with self.assertRaises(ValidationError):
            SceneCreate(name="Neither", brightness=50)

    def test_sequence_needs_two_steps(self):
        one = [SceneStep(color="#FF0000", brightness=50)]
        with self.assertRaises(ValidationError):
            SceneCreate(name="Short", kind="sequence", steps=one)


class StepTests(unittest.TestCase):
    def test_temperature_fades_stay_in_white_mode(self):
        state = step(color_temp=4000).blend(step(color_temp=2000 + 200), 0.5)
        self.assertEqual(state["color_temp"], 3100)

    def test_color_to_temperature_fades_through_rgb(self):
        state = step(brightness=100, color_temp=6500).blend(step(brightness=0 + 1, color="#000000"), 0.5)
        self.assertIn("color", state)
        self.assertEqual(state["brightness"], 50)

    def test_unknown_transition_is_instant(self):
        scene = {"steps": [{"color": "#FF0000", "brightness": 50, "hold_ms": 200, "transition_id": 99}]}
        self.assertEqual(Step.from_scene(scene, {})[0].fade_s, 0)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.frames = []

        async def send(ip, **state):
            self.frames.append((ip, state))

        self.engine = SceneEngine(send)
        self.engine.start()
        self.addCleanup(self.engine.close)

    def wait_until(self, condition, timeout=3.0):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.02)
        return condition()

    def test_plays_fade_frames_then_finishes_on_last_step(self):
        steps = [step(color="#000000", brightness=10), step(color="#FFFFFF", brightness=90, fade_s=0.36)]
        self.engine.play(1, steps, False, [{"id": 7, "ip_address": "10.0.0.7"}])
        self.assertEqual(self.engine.playing(), {7: 1})
        self.assertTrue(self.wait_until(lambda: not self.engine.playing()))
        self.assertEqual(self.frames[-1][1], {"brightness": 90, "color": "#FFFFFF"})
        self.assertGreaterEqual(len(self.frames), 3)  # first step + interpolated frames

    def test_looping_sequence_runs_until_stopped(self):
        steps = [step(color="#FF0000", hold_s=0.05), step(color="#0000FF", hold_s=0.05)]
        self.engine.play(2, steps, True, [{"id": 1, "ip_address": "a"}, {"id": 2, "ip_address": "b"}])
        self.assertTrue(self.wait_until(lambda: len(self.frames) >= 8))
        self.engine.stop([1])
        self.assertEqual(self.engine.playing(), {2: 2})
        self.engine.stop([2])
        count = len(self.frames)
        time.sleep(0.2)
        self.assertEqual(self.engine.playing(), {})
        self.assertLessEqual(len(self.frames) - count, 1)


class FakeEngine:
    def __init__(self): self.played, self.stopped, self.active = [], [], {}
    def play(self, scene_id, steps, loops, lights): self.played.append((scene_id, len(steps), loops, lights))
    def stop(self, ids): self.stopped.append(ids)
    def playing(self): return self.active


class FakeLights:
    def __init__(self): self.updates = []
    def targets(self, target_type, target_id): return [{"id": 3, "ip_address": "10.0.0.3"}]
    def update_state(self, light_id, **values): self.updates.append((light_id, values))


class FakeControl:
    UNSCOPED_TARGETS = ("all", "on")
    def __init__(self): self.lights, self.states = FakeLights(), []
    def resolve_targets(self, target_type, target_id): return self.lights.targets(target_type, target_id)
    async def control(self, target_type, target_id, state): self.states.append(state); return []


class FakeScenes:
    ROWS = {
        1: {"id": 1, "name": "Focus", "kind": "solid", "color": None, "color_temp": 5000,
            "brightness": 100, "steps": [], "loops": False, "is_preset": True},
        2: {"id": 2, "name": "Pulse", "kind": "sequence", "color": None, "color_temp": None,
            "brightness": None, "loops": True, "is_preset": False,
            "steps": [{"color_temp": 2700, "brightness": 100, "hold_ms": 300, "transition_id": 5},
                      {"color_temp": 2700, "brightness": 15, "hold_ms": 300, "transition_id": 5}]},
    }
    def get(self, scene_id): return self.ROWS.get(scene_id)
    def list(self): return list(self.ROWS.values())
    def delete(self, scene_id): return True


class FakeTransitions:
    def list(self): return [{"id": 5, "name": "Smooth", "duration_ms": 1500, "curve": "ease-in-out", "is_preset": True}]


class SceneServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.control = FakeEngine(), FakeControl()
        self.service = SceneService(FakeScenes(), TransitionService(FakeTransitions()), self.control, self.engine)

    def test_solid_scheme_sets_temperature_directly(self):
        asyncio.run(self.service.apply("all", None, 1))
        self.assertEqual((self.control.states[0].color_temp, self.control.states[0].brightness), (5000, 100))
        self.assertEqual(self.engine.played, [])

    def test_sequence_scheme_starts_playback_and_marks_lights_on(self):
        result = asyncio.run(self.service.apply("all", None, 2))
        self.assertEqual(self.engine.played[0][:3], (2, 2, True))
        self.assertEqual(self.control.lights.updates, [(3, {"on": True})])
        self.assertTrue(result["playing"])

    def test_apply_reports_only_the_targeted_lights(self):
        result = asyncio.run(self.service.apply("group", 23, 1))
        self.assertEqual(
            (result["target_type"], result["target_id"], result["light_ids"], result["playing"]),
            ("group", 23, [3], False),
        )

    def test_list_adds_previews_and_cycle_length(self):
        pulse = next(scene for scene in self.service.list() if scene["id"] == 2)
        self.assertEqual(len(pulse["preview_colors"]), 2)
        self.assertEqual(pulse["cycle_ms"], 2 * (300 + 1500))

    def test_built_in_schemes_cannot_be_deleted(self):
        with self.assertRaises(ValueError):
            self.service.delete(1)


class PresetTests(unittest.TestCase):
    def test_twelve_valid_presets_referencing_real_transitions(self):
        saved, transitions = [], []

        class Scenes:
            def upsert_preset(self, entry): saved.append(entry)

        class Transitions:
            def upsert_preset(self, entry): transitions.append(entry)
            def list(self): return [{"id": i, "name": t.name} for i, t in enumerate(transitions, 1)]

        PresetCatalog(Scenes(), Transitions()).install()
        self.assertEqual(len(saved), len(SOLIDS) + len(SEQUENCES))
        self.assertEqual(len(saved), 12)
        self.assertEqual(len(transitions), len(TRANSITIONS))
        sequences = [scene for scene in saved if scene.kind == "sequence"]
        self.assertTrue(all(step.transition_id for scene in sequences for step in scene.steps))


if __name__ == "__main__":
    unittest.main()
