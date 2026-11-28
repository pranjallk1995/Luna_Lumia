"""Shortcut keys and hotkeys.

Shortcut keys are your own named sets of keyboard keys ("Copy" = LeftCtrl and C): schemes, effects, and painting
use their names like the built-in groups (wasd, arrows). Hotkeys are key combinations pressed on the PC that runs
the iCUE bridge: Windows hands the combination to the bridge (RegisterHotKey), and Lumia, which long-polls the
bridge, plays a scheme on a target, or stops what plays there, or turns the lights off. Pressing a scheme's hotkey
while that scheme plays on all its lights stops it again. A hotkey can also open an app on the PC: the bridge opens
it itself, at once, from its own list of apps (Lumia only names one).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from app.core import tenancy
from app.core.errors import NotFoundError
from app.core.models import HotkeyCreate, KeyGroupCreate, LightState
from app.integrations.icue import KEY_GROUPS, ICueAdapter
from app.data.repositories import HotkeyRepository, KeyGroupRepository, Row

LOG = logging.getLogger("uvicorn.error")
UPDATE_BRIDGE = "This PC's iCUE bridge has no hotkeys yet: update it with bridge/install.ps1"


class ShortcutService:
    def __init__(self, groups: KeyGroupRepository, hotkeys: HotkeyRepository, scenes: Any, icue: ICueAdapter) -> None:
        self.groups, self.hotkeys, self.scenes, self.icue = groups, hotkeys, scenes, icue
        self.control = scenes.control
        # Bridge (host, port) -> what it last said about the hotkeys: registered, refused, or an error.
        self.bridge_status: dict[tuple[str, int], dict[str, Any]] = {}
        self.changed = threading.Event()  # wakes the hotkey worker to send the new list

    # Shortcut keys ------------------------------------------------------------------------------------------

    def key_groups(self) -> dict[str, tuple[str, ...]]:
        """Lower-case group name -> its keys: the built-in groups, then yours (a name of yours wins)."""
        groups = {name: tuple(keys) for name, keys in KEY_GROUPS.items()}
        for row in self.groups.list():
            groups[row["name"].casefold()] = tuple(row["keys"])
        return groups

    def list_groups(self) -> list[Row]:
        return self.groups.list()

    def _free_name(self, name: str, keep: int | None = None) -> None:
        if name.casefold() in KEY_GROUPS:
            raise ValueError(f"{name!r} is a built-in group; pick another name")
        same = [row for row in self.groups.list() if row["name"].casefold() == name.casefold() and row["id"] != keep]
        if same:
            raise ValueError(f"You already have shortcut keys named {same[0]['name']!r}")

    def add_group(self, entry: KeyGroupCreate) -> Row:
        self._free_name(entry.name)
        return self.groups.add(entry)

    def update_group(self, group_id: int, entry: KeyGroupCreate) -> Row:
        self._free_name(entry.name, group_id)
        row = self.groups.update(group_id, entry)
        if not row:
            raise NotFoundError("Shortcut keys not found")
        return row

    def delete_group(self, group_id: int) -> None:
        if not self.groups.delete(group_id):
            raise NotFoundError("Shortcut keys not found")

    # Hotkeys ------------------------------------------------------------------------------------------------

    def bridges(self) -> list[tuple[str, int]]:
        """Every PC with an iCUE bridge among your lights, as (host, port)."""
        found = {(str(light["ip_address"]), int(light.get("port") or 6743))
                 for light in self.control.lights.list() if light.get("protocol") == "icue"}
        return sorted(found)

    def combos(self) -> list[str]:
        """The enabled combinations Lumia acts on; ``opens`` has those the bridge opens apps for."""
        return [row["combo"] for row in self.hotkeys.list() if row["enabled"] and row["action"] != "open"]

    def opens(self) -> dict[str, str]:
        return {row["combo"]: row["app"] for row in self.hotkeys.list() if row["enabled"] and row["action"] == "open"}

    def apps(self) -> list[dict]:
        """Apps a hotkey can open, from the PCs' bridges (each app once)."""
        found: dict[str, dict] = {}
        for status in self.bridge_status.values():
            for app in status.get("apps") or []:
                found.setdefault(app["app"], app)
        return list(found.values())

    def _remember(self, bridge: tuple[str, int], reply: dict) -> dict:
        try:
            apps = self.icue.apps(*bridge)
        except Exception:  # noqa: BLE001 - an older bridge lists no apps
            apps = (self.bridge_status.get(bridge) or {}).get("apps") or []
        status = {"ok": True, "boot": reply.get("boot"), "refused": reply.get("refused") or {}, "apps": apps, "at": time.time()}
        self.bridge_status[bridge] = status
        return status

    def list_hotkeys(self) -> list[Row]:
        scenes = {scene["id"]: scene["name"] for scene in self.scenes.scenes.list()}
        labels = {app["app"]: app.get("label") or app["app"] for app in self.apps()}
        rows = []
        for row in self.hotkeys.list():
            row = dict(row)
            row["scene_name"] = scenes.get(row["scene_id"])
            row["app_label"] = labels.get(row.get("app"), row.get("app"))
            refused = [reason for status in self.bridge_status.values()
                       for combo, reason in (status.get("refused") or {}).items() if combo == row["combo"]]
            row["problem"] = refused[0] if refused else None
            rows.append(row)
        return rows

    def status(self) -> dict[str, Any]:
        bridges = []
        for host, port in self.bridges():
            status = self.bridge_status.get((host, port)) or {}
            bridges.append({"host": host, "port": port, "listening": status.get("ok", False),
                            "error": status.get("error"), "checked_at": status.get("at")})
        return {"key_groups": self.list_groups(), "hotkeys": self.list_hotkeys(), "bridges": bridges, "apps": self.apps(),
                "built_in_groups": {name: list(keys) for name, keys in KEY_GROUPS.items()}}

    def _check(self, entry: HotkeyCreate, keep: int | None = None) -> None:
        if entry.scene_id is not None:
            self.scenes.get(entry.scene_id)
        other = self.hotkeys.by_combo(entry.combo)
        if other and other["id"] != keep:
            raise ValueError(f"{entry.combo} is already a hotkey")
        if entry.target_type not in ("all", "on"):
            self.control.resolve_targets(entry.target_type, entry.target_id)

    def push(self) -> None:
        """Send every bridge the enabled hotkeys now, so a new one works at once (the worker keeps them in step)."""
        self.changed.set()
        combos, opens = self.combos(), self.opens()
        for bridge in self.bridges():
            try:
                reply = self.icue.set_hotkeys(*bridge, combos, opens)
            except LookupError:
                self.bridge_status[bridge] = {"ok": False, "error": UPDATE_BRIDGE, "at": time.time()}
            except Exception as error:  # noqa: BLE001 - shown with the bridge's status
                self.bridge_status[bridge] = {"ok": False, "error": str(error), "at": time.time()}
            else:
                self._remember(bridge, reply)

    def add_hotkey(self, entry: HotkeyCreate) -> Row:
        self._check(entry)
        row = self.hotkeys.add(entry)
        self.push()
        return row

    def update_hotkey(self, hotkey_id: int, entry: HotkeyCreate) -> Row:
        self._check(entry, hotkey_id)
        row = self.hotkeys.update(hotkey_id, entry)
        if not row:
            raise NotFoundError("Hotkey not found")
        self.push()
        return row

    def delete_hotkey(self, hotkey_id: int) -> None:
        if not self.hotkeys.delete(hotkey_id):
            raise NotFoundError("Hotkey not found")
        self.push()

    async def press(self, combo: str) -> dict[str, Any] | None:
        """Do what a hotkey does; None when no enabled hotkey has that combination."""
        row = self.hotkeys.by_combo(combo)
        if not row or not row["enabled"]:
            return None
        return await self.run(row)

    async def press_id(self, hotkey_id: int) -> dict[str, Any]:
        row = self.hotkeys.get(hotkey_id)
        if not row:
            raise NotFoundError("Hotkey not found")
        return await self.run(row)

    async def run(self, row: Row) -> dict[str, Any]:
        self.hotkeys.mark_pressed(row["id"])
        if row["action"] == "open":
            # Tried from the page or an assistant: the bridges open it (a press on the PC already did).
            opened = []
            for bridge in self.bridges():
                await asyncio.to_thread(self.icue.open_app, *bridge, row["app"])
                opened.append(bridge[0])
            if not opened:
                raise ValueError("No PC with the iCUE bridge to open it on")
            return {"combo": row["combo"], "action": "open", "app": row["app"], "opened_on": opened}
        target_type, target_id = row["target_type"], row["target_id"]
        LOG.info("Hotkey %s: %s on %s %s", row["combo"], row["action"], target_type, target_id)
        if row["action"] == "off":
            results = await self.control.control(target_type, target_id, LightState(on=False))
            return {"combo": row["combo"], "action": "off", "light_ids": [item["light"]["id"] for item in results]}
        if row["action"] == "stop":
            return {"combo": row["combo"], "action": "stop", **self.scenes.stop(target_type, target_id)}
        lights = self.control.resolve_targets(target_type, target_id)
        playing = self.scenes.playing()
        if lights and all(playing.get(light["id"]) == row["scene_id"] for light in lights):
            return {"combo": row["combo"], "action": "stop", **self.scenes.stop(target_type, target_id)}
        applied = await self.scenes.apply(target_type, target_id, row["scene_id"])
        return {"combo": row["combo"], "action": "scene", "scene": applied["scene"], "light_ids": applied["light_ids"]}


class HotkeyWorker:
    """One thread per PC bridge: send it the hotkeys, then wait for presses and act on them."""

    POLL_SECONDS = 20
    RETRY_SECONDS = 30
    SCAN_SECONDS = 60

    def __init__(self, shortcuts: ShortcutService) -> None:
        self.shortcuts = shortcuts
        self.stop_event = threading.Event()
        self.threads: dict[tuple[str, int], threading.Thread] = {}

    def start(self) -> None:
        threading.Thread(target=self.run, daemon=True, name="lumia-hotkeys").start()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        with tenancy.acting_as(tenancy.OWNER):
            while not self.stop_event.is_set():
                try:
                    for bridge in self.shortcuts.bridges():
                        if bridge not in self.threads or not self.threads[bridge].is_alive():
                            self.threads[bridge] = threading.Thread(
                                target=self.follow, args=bridge, daemon=True, name=f"lumia-hotkeys-{bridge[0]}")
                            self.threads[bridge].start()
                except Exception as error:  # noqa: BLE001 - the database may be starting
                    LOG.warning("Hotkeys: could not list the PC bridges: %s", error)
                self.stop_event.wait(self.SCAN_SECONDS)

    def follow(self, host: str, port: int) -> None:
        with tenancy.acting_as(tenancy.OWNER):
            sent: tuple | None = None
            after = None
            while not self.stop_event.is_set():
                if (host, port) not in self.shortcuts.bridges():
                    self.shortcuts.bridge_status.pop((host, port), None)
                    return
                try:
                    combos, opens = self.shortcuts.combos(), self.shortcuts.opens()
                    self.shortcuts.changed.clear()
                    boot = (self.shortcuts.bridge_status.get((host, port)) or {}).get("boot")
                    if sent != (combos, opens, boot):
                        reply = self.shortcuts.icue.set_hotkeys(host, port, combos, opens)
                        refused = self.shortcuts._remember((host, port), reply)["refused"]
                        sent = (combos, opens, reply.get("boot"))
                        if refused:
                            LOG.warning("Hotkeys refused on %s: %s", host, refused)
                    reply = self.shortcuts.icue.hotkey_presses(host, port, after, self.POLL_SECONDS)
                    status = self.shortcuts.bridge_status[(host, port)]
                    if reply.get("boot") != status.get("boot"):
                        status["boot"], after = reply.get("boot"), None  # it restarted: send the list again
                        sent = None
                        continue
                    status["at"] = time.time()
                    if after is not None:
                        for press in reply.get("presses") or []:
                            if "opened" in press or "error" in press:  # an app the bridge opened itself
                                row = self.shortcuts.hotkeys.by_combo(press["combo"])
                                if row:
                                    self.shortcuts.hotkeys.mark_pressed(row["id"])
                                continue
                            try:
                                asyncio.run(self.shortcuts.press(press["combo"]))
                            except Exception as error:  # noqa: BLE001 - one failed press must not stop the rest
                                LOG.warning("Hotkey %s failed: %s", press.get("combo"), error)
                    after = reply.get("seq", after)
                except LookupError:
                    self.shortcuts.bridge_status[(host, port)] = {"ok": False, "error": UPDATE_BRIDGE, "at": time.time()}
                    sent = None
                    self.stop_event.wait(self.RETRY_SECONDS * 10)
                except Exception as error:  # noqa: BLE001 - the PC is asleep or the bridge restarting
                    self.shortcuts.bridge_status[(host, port)] = {"ok": False, "error": str(error), "at": time.time()}
                    sent = None
                    # A change to the hotkeys is worth trying again at once.
                    self.shortcuts.changed.wait(self.RETRY_SECONDS)
