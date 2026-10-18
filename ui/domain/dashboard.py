"""Read-only view model over the backend's dashboard payload."""

from dataclasses import dataclass, field
from typing import Any

Item = dict[str, Any]


@dataclass
class Dashboard:
    """Expose dashboard collections plus the lookups the tabs share."""

    lights: list[Item]
    rooms: list[Item]
    groups: list[Item]
    scenes: list[Item]
    schedules: list[Item]
    transitions: list[Item] = field(default_factory=list)
    playing: dict[int, int] = field(default_factory=dict)  # light id -> playing scheme id
    room_names_by_light: dict[int, list[str]] = field(init=False)

    def __post_init__(self) -> None:
        self.light_by_id = {light["id"]: light for light in self.lights}
        self.room_names_by_light = {light["id"]: [] for light in self.lights}
        for room in self.rooms:
            for light_id in room["light_ids"]:
                if light_id in self.room_names_by_light:
                    self.room_names_by_light[light_id].append(room["name"])

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "Dashboard":
        return cls(
            lights=data["lights"],
            rooms=data.get("rooms", []),
            groups=data.get("groups", []),
            scenes=data["scenes"],
            schedules=data["schedules"],
            transitions=data.get("transitions", []),
            playing={int(light_id): scene_id for light_id, scene_id in data.get("playing", {}).items()},
        )

    def target_options(self) -> dict[str, tuple[str, int | None]]:
        """Map target labels to API (target_type, target_id); rooms are groups."""
        return (
            {"All lights": ("all", None)}
            | {f'Light · {item["name"]}': ("light", item["id"]) for item in self.lights}
            | {f'Room · {item["name"]}': ("group", item["id"]) for item in self.rooms}
            | {f'Group · {item["name"]}': ("group", item["id"]) for item in self.groups}
        )

    def lights_playing(self, scene_id: int) -> int:
        return sum(1 for playing in self.playing.values() if playing == scene_id)

    @property
    def collections(self) -> list[Item]:
        return [*self.rooms, *self.groups]

    @property
    def all_on(self) -> bool:
        return bool(self.lights) and all(light["is_on"] for light in self.lights)

    @property
    def configured_ips(self) -> set[str]:
        return {light["ip_address"] for light in self.lights}

    def light_name(self, light_id: int) -> str:
        return self.light_by_id[light_id]["name"]

    def has_room(self, light_id: int) -> bool:
        return bool(self.room_names_by_light.get(light_id))

    def unassigned_light_ids(self) -> list[int]:
        return [light["id"] for light in self.lights if not self.has_room(light["id"])]

    def member_lights(self, collection: Item) -> list[Item]:
        return [light for light in self.lights if light["id"] in collection["light_ids"]]

    def addable_light_ids(self, collection: Item) -> list[int]:
        """Lights not yet in the collection; rooms also exclude lights in other rooms."""
        return [
            light["id"]
            for light in self.lights
            if light["id"] not in collection["light_ids"]
            and (collection["kind"] == "group" or not self.has_room(light["id"]))
        ]
