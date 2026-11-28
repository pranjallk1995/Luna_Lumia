"""Effects (blink, strobe, breathe, glow, rainbow), shortcut keys, and hotkeys."""

import asyncio
import time
import unittest

from pydantic import ValidationError

from app.core.models import HotkeyCreate, KeyGroupCreate, SceneCreate, normalize_hotkey
from app.services.playback import Motion, SceneEngine, Step, expand_groups
from app.services.shortcuts import ShortcutService


def motion(kind, keys=None, period=1.0, stagger=0.0, color=None, to=None):
    return Motion(kind, tuple(keys) if keys else None, color, to, period, stagger)


def step(color="#FF0000", brightness=80, keys=None, effects=(), hold=0.0):
    return Step(color, None, brightness, hold, 0.0, "linear", keys, tuple(effects))


class EffectModelTests(unittest.TestCase):
    def test_one_step_with_an_effect_is_a_sequence(self):
        scheme = SceneCreate(name="Blink", kind="sequence", steps=[
            {"color": "#ff0000", "brightness": 80, "hold_ms": 0, "effects": [{"type": "blink", "to": "#00ff00"}]}])
        self.assertEqual(scheme.steps[0].effects[0].to, "#00FF00")

    def test_one_still_step_is_still_too_short(self):
        with self.assertRaises(ValidationError):
            SceneCreate(name="Still", kind="sequence", steps=[{"color": "#FF0000", "brightness": 80}])

    def test_effects_on_keys_need_a_per_key_scheme(self):
        effect = {"type": "blink", "keys": ["Escape"]}
        with self.assertRaises(ValidationError):
            SceneCreate(name="Esc", kind="sequence", steps=[{"color": "#000000", "brightness": 80, "effects": [effect]}])
        scheme = SceneCreate(name="Esc", kind="keys", steps=[{"color": "#000000", "brightness": 80, "effects": [effect]}])
        self.assertEqual(scheme.steps[0].effects[0].keys, ["Escape"])

    def test_effects_are_checked(self):
        for bad in ({"type": "spin"}, {"type": "blink", "period_ms": 50}, {"type": "blink", "keys": []},
                    {"type": "glow", "color": "red"}):
            with self.assertRaises(ValidationError, msg=bad):
                SceneCreate(name="Bad", kind="sequence", steps=[{"color": "#FF0000", "brightness": 80, "effects": [bad]}])


class MotionTests(unittest.TestCase):
    def test_blink_is_on_for_half_of_each_period(self):
        blink = motion("blink")
        self.assertEqual([blink.level(t) for t in (0, 0.4, 0.6, 1.1)], [1, 1, 0, 1])
        self.assertAlmostEqual(blink.until_change(0.1), 0.4)

    def test_strobe_flashes_briefly(self):
        strobe = motion("strobe", period=2.0)
        self.assertEqual(strobe.level(0.1), 1)
        self.assertEqual(strobe.level(1.0), 0)

    def test_breathe_swells_smoothly(self):
        breathe = motion("breathe")
        self.assertAlmostEqual(breathe.level(0), 1)
        self.assertAlmostEqual(breathe.level(0.5), 0)
        self.assertAlmostEqual(breathe.level(0.25), 0.5)

    def test_stagger_moves_each_key_later(self):
        blink = motion("blink", ["Q", "W", "E"], stagger=0.5)
        self.assertEqual([blink.level(0.1, index) for index in range(3)], [1, 0, 1])

    def test_a_key_effect_leaves_other_keys_as_the_step_colors_them(self):
        frame = step(keys={"A": "#0000FF"}, effects=[motion("blink", ["Escape"], color="#FFFFFF")]).render(0.6)
        self.assertEqual(frame["keys"], {"A": "#0000FF", "Escape": "#000000"})
        self.assertEqual(frame["color"], "#FF0000")

    def test_glow_dims_a_key_to_a_third_not_black(self):
        frame = step(keys={}, effects=[motion("glow", ["W"])]).render(0.5)
        self.assertEqual(frame["keys"]["W"], "#540000")

    def test_rainbow_turns_through_the_hues(self):
        rainbow = motion("rainbow", ["A"], period=3.0)
        self.assertEqual([rainbow.toward("#000000", t) for t in (0, 1, 2)], ["#FF0000", "#00FF00", "#0000FF"])

    def test_a_whole_light_blink_turns_the_light_off_and_on(self):
        blinking = step(effects=[motion("blink")])
        self.assertEqual(blinking.render(0.1), {"brightness": 80, "color": "#FF0000"})
        self.assertEqual(blinking.render(0.6)["color"], "#000000")

    def test_a_whole_light_breathe_dims_the_brightness_since_bulbs_cannot_show_dim_colors(self):
        frame = step(brightness=80, effects=[motion("breathe")]).render(0.25)
        self.assertEqual(frame, {"brightness": 40, "color": "#FF0000"})

    def test_a_whole_light_blink_between_two_colors_mixes_them(self):
        frame = step(effects=[motion("blink", to="#00FF00")]).render(0.6)
        self.assertEqual(frame["color"], "#00FF00")

    def test_your_groups_spread_over_their_keys_and_a_named_key_wins(self):
        groups = {"copy": ("LeftCtrl", "C")}
        self.assertEqual(expand_groups({"copy": "#FF0000", "C": "#00FF00"}, groups),
                         {"LeftCtrl": "#FF0000", "C": "#00FF00"})
        scene = {"steps": [{"color": "#000000", "brightness": 80, "effects": [{"type": "blink", "keys": ["copy"]}]}]}
        self.assertEqual(Step.from_scene(scene, {}, groups)[0].effects[0].keys, ("LeftCtrl", "C"))


class EnginePlaysEffectsTests(unittest.TestCase):
    def test_a_blinking_step_is_sent_on_and_off_until_stopped(self):
        frames = []

        async def send(address, **state):
            frames.append((time.monotonic(), state.get("color")))

        engine = SceneEngine(send)
        engine.start()
        try:
            blinking = step(effects=[motion("blink", period=0.3)])
            engine.play(1, [blinking], True, [{"id": 1, "ip_address": "10.0.0.2"}])
            time.sleep(1.0)
            engine.stop([1])
        finally:
            engine.close()
        colors = [color for _, color in frames]
        self.assertIn("#000000", colors)
        self.assertIn("#FF0000", colors)
        changes = sum(1 for a, b in zip(colors, colors[1:]) if a != b)
        self.assertGreaterEqual(changes, 4)


class HotkeyModelTests(unittest.TestCase):
    def test_combos_are_written_one_way(self):
        self.assertEqual(normalize_hotkey("alt + ctrl + 1"), "Ctrl+Alt+1")
        self.assertEqual(normalize_hotkey("win+shift+l"), "Shift+Win+L")
        self.assertEqual(normalize_hotkey("Control+Esc"), "Ctrl+Escape")
        self.assertEqual(normalize_hotkey("F9"), "F9")
        self.assertEqual(normalize_hotkey("ctrl+alt+f"), "Ctrl+Alt+F")
        with self.assertRaises(ValueError):
            normalize_hotkey("F")
        self.assertEqual(normalize_hotkey("MediaPlayPause"), "MediaPlayPause")

    def test_combos_that_would_eat_typing_are_refused(self):
        for combo in ("A", "Shift+A", "Ctrl+Alt", "Ctrl+A+B", "Ctrl+Banana", ""):
            with self.assertRaises(ValueError, msg=combo):
                normalize_hotkey(combo)

    def test_a_scheme_hotkey_needs_its_scheme_and_a_target_its_id(self):
        with self.assertRaises(ValidationError):
            HotkeyCreate(combo="Ctrl+Alt+1")
        with self.assertRaises(ValidationError):
            HotkeyCreate(combo="Ctrl+Alt+1", scene_id=3, target_type="group")
        stop = HotkeyCreate(combo="Ctrl+Alt+0", action="stop", scene_id=3)
        self.assertIsNone(stop.scene_id)

    def test_shortcut_key_names_are_tidy(self):
        group = KeyGroupCreate(name="  Copy   paste ", keys=["LeftCtrl", "C", "C", "V"])
        self.assertEqual((group.name, group.keys), ("Copy paste", ["LeftCtrl", "C", "V"]))
        with self.assertRaises(ValidationError):
            KeyGroupCreate(name="Copy!", keys=["C"])


class FakeRows:
    def __init__(self, rows=()):
        self.rows = {row["id"]: dict(row) for row in rows}

    def list(self): return list(self.rows.values())
    def get(self, row_id): return self.rows.get(row_id)
    def by_combo(self, combo): return next((r for r in self.rows.values() if r["combo"] == combo), None)
    def mark_pressed(self, row_id): self.rows[row_id]["pressed"] = True

    def add(self, entry):
        row = {"id": len(self.rows) + 1, **entry.model_dump()}
        if "scene_id" in row:
            row["scene_id"] = entry.scene_id
        self.rows[row["id"]] = row
        return row

    def delete(self, row_id): return self.rows.pop(row_id, None) is not None


class FakeLightsRepo:
    def list(self): return [{"id": 1, "protocol": "icue", "ip_address": "192.168.1.5", "port": None},
                            {"id": 2, "protocol": "wiz", "ip_address": "192.168.1.9"}]


class FakeControl:
    lights = FakeLightsRepo()

    def resolve_targets(self, target_type, target_id):
        return [{"id": 1}, {"id": 2}]


class FakeScenes:
    def __init__(self):
        self.control = FakeControl()
        self.scenes = FakeRows([{"id": 3, "name": "Party"}])
        self.now_playing, self.calls = {}, []

    def get(self, scene_id): return self.scenes.get(scene_id)
    def playing(self): return self.now_playing

    async def apply(self, target_type, target_id, scene_id):
        self.calls.append(("apply", scene_id))
        self.now_playing = {1: scene_id, 2: scene_id}
        return {"scene": "Party", "light_ids": [1, 2]}

    def stop(self, target_type, target_id):
        self.calls.append(("stop",))
        self.now_playing = {}
        return {"stopped_light_ids": [1, 2]}


class FakeICue:
    def __init__(self):
        self.sent = []

    def set_hotkeys(self, host, port, combos, opens=None):
        self.sent.append((host, port, combos, opens or {}))
        return {"boot": "b1", "registered": combos[1:], "refused": {combos[0]: "another program already uses it"} if combos else {}}

    def apps(self, host, port):
        return [{"app": "vscode", "label": "Visual Studio Code"}]

    def open_app(self, host, port, app):
        self.sent.append(("open", app))
        return {"ok": True}


class ShortcutServiceTests(unittest.TestCase):
    def setUp(self):
        self.icue, self.scenes = FakeICue(), FakeScenes()
        self.service = ShortcutService(FakeRows(), FakeRows(), self.scenes, self.icue)

    def test_your_groups_join_the_built_in_ones_and_cannot_take_their_names(self):
        self.service.add_group(KeyGroupCreate(name="Copy", keys=["LeftCtrl", "C"]))
        self.assertEqual(self.service.key_groups()["copy"], ("LeftCtrl", "C"))
        self.assertIn("wasd", self.service.key_groups())
        with self.assertRaises(ValueError):
            self.service.add_group(KeyGroupCreate(name="WASD", keys=["W"]))
        with self.assertRaises(ValueError):
            self.service.add_group(KeyGroupCreate(name="copy", keys=["C"]))

    def test_a_new_hotkey_reaches_the_pc_bridge_at_once_and_a_refusal_is_shown(self):
        self.service.add_hotkey(HotkeyCreate(combo="Ctrl+Alt+1", scene_id=3))
        self.assertEqual(self.icue.sent, [("192.168.1.5", 6743, ["Ctrl+Alt+1"], {})])
        listed = self.service.list_hotkeys()[0]
        self.assertEqual((listed["scene_name"], listed["problem"]), ("Party", "another program already uses it"))
        self.assertTrue(self.service.status()["bridges"][0]["listening"])

    def test_pressing_a_scheme_hotkey_plays_it_and_pressing_again_stops_it(self):
        self.service.add_hotkey(HotkeyCreate(combo="Ctrl+Alt+1", scene_id=3))
        first = asyncio.run(self.service.press("Ctrl+Alt+1"))
        second = asyncio.run(self.service.press("Ctrl+Alt+1"))
        self.assertEqual((first["action"], second["action"]), ("scene", "stop"))
        self.assertEqual(self.scenes.calls, [("apply", 3), ("stop",)])

    def test_an_unknown_or_disabled_combo_does_nothing(self):
        self.service.add_hotkey(HotkeyCreate(combo="Ctrl+Alt+2", scene_id=3, enabled=False))
        self.assertIsNone(asyncio.run(self.service.press("Ctrl+Alt+2")))
        self.assertIsNone(asyncio.run(self.service.press("Ctrl+Alt+9")))
        self.assertEqual(self.scenes.calls, [])
        self.assertEqual(self.icue.sent[-1][2], [])


if __name__ == "__main__":
    unittest.main()


class OpenAppTests(unittest.TestCase):
    def setUp(self):
        self.icue, self.scenes = FakeICue(), FakeScenes()
        self.service = ShortcutService(FakeRows(), FakeRows(), self.scenes, self.icue)

    def test_an_app_hotkey_goes_to_the_bridge_to_open_there_and_lists_its_label(self):
        self.service.add_hotkey(HotkeyCreate(combo="Ctrl+Alt+V", action="open", app="vscode"))
        self.assertEqual(self.icue.sent[-1][2:], ([], {"Ctrl+Alt+V": "vscode"}))
        self.assertEqual(self.service.list_hotkeys()[0]["app_label"], "Visual Studio Code")
        self.assertEqual(self.service.status()["apps"], [{"app": "vscode", "label": "Visual Studio Code"}])

    def test_trying_it_from_lumia_asks_the_pc_to_open_it(self):
        self.service.add_hotkey(HotkeyCreate(combo="Ctrl+Alt+V", action="open", app="vscode"))
        result = asyncio.run(self.service.press_id(1))
        self.assertEqual((result["app"], self.icue.sent[-1]), ("vscode", ("open", "vscode")))
        self.assertEqual(self.scenes.calls, [])

    def test_an_app_hotkey_needs_a_listed_style_name_and_no_target(self):
        with self.assertRaises(ValidationError):
            HotkeyCreate(combo="Ctrl+Alt+V", action="open")
        with self.assertRaises(ValidationError):
            HotkeyCreate(combo="Ctrl+Alt+V", action="open", app="C:\\evil.exe")
        hotkey = HotkeyCreate(combo="Ctrl+Alt+V", action="open", app="vscode", target_type="light", target_id=2)
        self.assertEqual((hotkey.target_type, hotkey.target_id), ("all", None))
