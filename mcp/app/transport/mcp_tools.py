"""MCP tools that let LLM clients manage Luna Lumia lights."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.integrations.devices import GLOBAL_BROADCAST
from app.core.models import (
    GroupCreate,
    GroupMembersUpdate,
    GroupUpdate,
    LightImageUpdate,
    LightState,
    LocationUpdate,
    RoomImageUpdate,
    SceneCreate,
    ScheduleCreate,
    TransitionCreate,
)
from app.services.application import LumiaService


class LumiaMCPTools:
    """Register Luna Lumia's MCP tool surface on a FastMCP server."""

    def __init__(self, server: FastMCP, service: LumiaService) -> None:
        self.server = server
        self.service = service
        self._register_inventory_tools()
        self._register_image_tools()
        self._register_scheme_tools()
        self._register_control_tools()
        self._register_schedule_tools()

    def _register_inventory_tools(self) -> None:
        server, lights, collections = self.server, self.service.lights, self.service.collections

        @server.tool()
        def list_lights():
            """List configured Luna Lumia lights and their last known states (see refresh_light_statuses)."""
            return lights.list()

        @server.tool()
        async def refresh_light_statuses():
            """Ask every light for its current power, brightness, color, and reachability, and save it.

            Lumia does not poll in the background, so call this before relying on
            list_lights if a light may have been changed outside Lumia. A light that
            moved to a new IP address is found again by its MAC address.
            """
            return await self.service.refresh_lights()

        @server.tool()
        def list_rooms():
            """List available rooms, their member lights, and background images."""
            return collections.list_with_images("room")

        @server.tool()
        def list_groups():
            """List available reusable groups, their member lights, and background images."""
            return collections.list_with_images("group")

        @server.tool()
        def get_room(room_id: int):
            """Get one room by id."""
            return collections.get(room_id, "room")

        @server.tool()
        def get_group(group_id: int):
            """Get one reusable group by id."""
            return collections.get(group_id, "group")

        @server.tool()
        def create_room(name: str, light_ids: list[int]):
            """Create a room. A light can belong to only one room."""
            return collections.create(GroupCreate(name=name, light_ids=light_ids), "room")

        @server.tool()
        def create_group(name: str, light_ids: list[int]):
            """Create a reusable group. Lights may belong to multiple groups."""
            return collections.create(GroupCreate(name=name, light_ids=light_ids), "group")

        @server.tool()
        def rename_room(room_id: int, name: str):
            """Rename a room and refresh its inferred background image."""
            entry = GroupUpdate(name=name)
            return collections.rename(room_id, "room", entry.name)

        @server.tool()
        def rename_group(group_id: int, name: str):
            """Rename a reusable group."""
            entry = GroupUpdate(name=name)
            return collections.rename(group_id, "group", entry.name)

        @server.tool()
        def add_lights_to_room(room_id: int, light_ids: list[int]):
            """Add lights to a room. Lights already assigned to another room are rejected."""
            entry = GroupMembersUpdate(light_ids=light_ids)
            return collections.add_members(room_id, "room", entry.light_ids)

        @server.tool()
        def add_lights_to_group(group_id: int, light_ids: list[int]):
            """Add lights to a group. The same lights may also belong to other groups."""
            entry = GroupMembersUpdate(light_ids=light_ids)
            return collections.add_members(group_id, "group", entry.light_ids)

        @server.tool()
        def remove_light_from_room(room_id: int, light_id: int):
            """Remove one light from a room without deleting the light."""
            collections.remove_member(room_id, "room", light_id)
            return {"removed": True, "room_id": room_id, "light_id": light_id}

        @server.tool()
        def remove_light_from_group(group_id: int, light_id: int):
            """Remove one light from a group without deleting the light."""
            collections.remove_member(group_id, "group", light_id)
            return {"removed": True, "group_id": group_id, "light_id": light_id}

        @server.tool()
        def delete_room(room_id: int):
            """Delete a room without deleting its lights."""
            collections.delete(room_id, "room")
            return {"deleted": True, "room_id": room_id}

        @server.tool()
        def delete_group(group_id: int):
            """Delete a reusable group without deleting its lights."""
            collections.delete(group_id, "group")
            return {"deleted": True, "group_id": group_id}

        @server.tool()
        async def discover_lights_on_network(broadcast_space: str = GLOBAL_BROADCAST):
            """Scan the local network for WiZ-compatible smart lights."""
            return await lights.discover(broadcast_space)

    def _register_image_tools(self) -> None:
        server, images = self.server, self.service.images

        @server.tool()
        def list_room_images():
            """List the room background image URLs used by Lumia light cards."""
            return images.list_room_images()

        @server.tool()
        def update_room_image(room_key: str, image_url: str):
            """Add or update the image URL used for a Lumia room type."""
            entry = RoomImageUpdate(room_key=room_key, image_url=image_url)
            return images.update_room_image(entry.room_key, entry.image_url)

        @server.tool()
        def set_light_background_image(
            light_id: int,
            image_url: str | None = None,
            room_name: str | None = None,
        ):
            """Assign a light image. Without a URL, infer it from room_name or the light name while preserving the available image scheme."""
            entry = LightImageUpdate(image_url=image_url)
            return images.apply_light_image(light_id, entry.image_url, room_name)

        @server.tool()
        def clear_light_background_image(light_id: int):
            """Clear a light-specific image override so the dashboard resolves its room image dynamically."""
            return images.set_light_image(light_id, None)

        @server.tool()
        def set_room_background_image(
            group_id: int,
            image_url: str | None = None,
            room_name: str | None = None,
        ):
            """Assign a room card image. Without a URL, infer it from the room name or member-light names and match the existing Visia image scheme."""
            entry = LightImageUpdate(image_url=image_url)
            return images.apply_collection_image(group_id, entry.image_url, room_name)

    def _register_scheme_tools(self) -> None:
        server, scenes, transitions = self.server, self.service.scenes, self.service.transitions

        @server.tool()
        def list_schemes():
            """List color schemes (solid and sequence), transitions, and what is playing per light."""
            return {
                "schemes": scenes.list(),
                "transitions": transitions.list(),
                "playing": scenes.playing(),
            }

        @server.tool()
        def create_solid_scheme(
            name: str, brightness: int, color: str | None = None, color_temp: int | None = None
        ):
            """Save a solid scheme: one #RRGGBB color or one white color_temp (2200-6500 K)."""
            return scenes.add(
                SceneCreate(name=name, brightness=brightness, color=color, color_temp=color_temp)
            )

        @server.tool()
        def create_sequence_scheme(name: str, steps: list[dict[str, Any]], loops: bool = True):
            """Save a sequence scheme of 2-24 steps that play in order (and repeat if loops).

            Each step: {"color": "#RRGGBB"} or {"color_temp": 2200-6500}, "brightness" 1-100,
            "hold_ms" (time to stay on the step), and "transition_id" (the fade into the step;
            see list_schemes for transitions; omit for an instant change).
            """
            return scenes.add(SceneCreate(name=name, kind="sequence", steps=steps, loops=loops))

        @server.tool()
        def update_solid_scheme(
            scheme_id: int, name: str, brightness: int, color: str | None = None, color_temp: int | None = None
        ):
            """Replace one of your solid schemes (built-ins cannot be edited); same fields as create_solid_scheme."""
            return scenes.update(
                scheme_id,
                SceneCreate(name=name, brightness=brightness, color=color, color_temp=color_temp),
            )

        @server.tool()
        def update_sequence_scheme(scheme_id: int, name: str, steps: list[dict[str, Any]], loops: bool = True):
            """Replace one of your sequence schemes (built-ins cannot be edited); same fields as create_sequence_scheme.

            A sequence that is playing restarts with the new steps.
            """
            return scenes.update(scheme_id, SceneCreate(name=name, kind="sequence", steps=steps, loops=loops))

        @server.tool()
        def update_transition(transition_id: int, name: str, duration_ms: int, curve: str = "ease-in-out"):
            """Replace one of your transitions (built-ins cannot be edited); same fields as create_transition."""
            return transitions.update(
                transition_id, TransitionCreate(name=name, duration_ms=duration_ms, curve=curve)
            )

        @server.tool()
        def create_transition(name: str, duration_ms: int, curve: str = "ease-in-out"):
            """Save a reusable fade: duration_ms (0-600000) and curve (linear, ease-in, ease-out, ease-in-out)."""
            return transitions.add(TransitionCreate(name=name, duration_ms=duration_ms, curve=curve))

        @server.tool()
        async def apply_scheme(
            scheme_id: int, target_type: str = "all", target_id: int | None = None
        ):
            """Apply a scheme to all lights, one light, or a room/group.

            Use target_type "all", "light", or "group". Rooms and groups both use
            "group" with their collection id.
            """
            return await scenes.apply(target_type, target_id, scheme_id)

        @server.tool()
        def stop_scheme(target_type: str = "all", target_id: int | None = None):
            """Stop sequence schemes on all lights, one light, or a room/group."""
            return scenes.stop(target_type, target_id)

        @server.tool()
        def delete_scheme(scheme_id: int):
            """Delete a user-created light scheme. Built-in schemes are protected."""
            scenes.delete(scheme_id)
            return {"deleted": True, "scheme_id": scheme_id}

        @server.tool()
        def delete_transition(transition_id: int):
            """Delete a user-created transition. Built-in transitions are protected."""
            transitions.delete(transition_id)
            return {"deleted": True, "transition_id": transition_id}

    def _register_control_tools(self) -> None:
        server, control, scenes = self.server, self.service.control, self.service.scenes

        @server.tool()
        async def set_light(
            light_id: int,
            on: bool | None = None,
            brightness: int | None = None,
            color: str | None = None,
            color_temp: int | None = None,
        ):
            """Control one light by id. Color is a #RRGGBB value; color_temp is white light in Kelvin (2200-6500). Set one of color or color_temp."""
            state = LightState(on=on, brightness=brightness, color=color, color_temp=color_temp)
            return await control.control("light", light_id, state)

        @server.tool()
        async def set_all_lights(on: bool):
            """Turn all configured lights on or off."""
            return await control.control("all", None, LightState(on=on))

        @server.tool()
        async def set_group(
            group_id: int,
            on: bool | None = None,
            brightness: int | None = None,
            color: str | None = None,
            color_temp: int | None = None,
        ):
            """Control every light in a saved group. Set one of color (#RRGGBB) or color_temp (Kelvin, 2200-6500)."""
            state = LightState(on=on, brightness=brightness, color=color, color_temp=color_temp)
            return await control.control("group", group_id, state)

        @server.tool()
        async def activate_scene(scene_id: int, target_type: str = "all", target_id: int | None = None):
            """Apply a saved scheme to "all" lights, one "light", or a "group" (rooms are groups).

            Solid schemes are set at once; sequence schemes start playing (and loop if set)
            until stopped or the lights are changed manually.
            """
            return await scenes.apply(target_type, target_id, scene_id)

        @server.tool()
        def stop_scene(target_type: str = "all", target_id: int | None = None):
            """Stop sequence schemes playing on "all" lights, one "light", or a "group"."""
            return scenes.stop(target_type, target_id)

    def _register_schedule_tools(self) -> None:
        server = self.server

        def schedules():
            # Resolved when a tool runs, not at registration.
            return self.service.schedules

        @server.tool()
        def get_location():
            """The saved location for sunrise/sunset schedules, with today's sunrise and sunset (HH:MM)."""
            return schedules().location.today()

        @server.tool()
        def set_location(name: str, latitude: float, longitude: float):
            """Save the location (decimal latitude/longitude) used to compute sunrise and sunset."""
            schedules().location.save(LocationUpdate(name=name, latitude=latitude, longitude=longitude))
            return schedules().location.today()

        @server.tool()
        def list_schedules():
            """List schedules and alarms, each with its time today ("today_time", HH:MM)."""
            return schedules().list()

        @server.tool()
        def create_schedule(
            name: str,
            action: str,
            time_mode: str = "time",
            run_time: str | None = None,
            offset_minutes: int = 0,
            target_type: str = "all",
            target_id: int | None = None,
            scene_id: int | None = None,
            weekdays: list[int] | None = None,
            kind: str = "schedule",
        ):
            """Create a recurring schedule or alarm.

            action: "on", "off", or "scene" (with scene_id). time_mode: "time" (run_time
            "HH:MM"), "sunrise", or "sunset" (offset_minutes -180..180, e.g. -30 = 30 min
            before; needs set_location first). target_type: "all", "light", or "group"
            (rooms are groups) with target_id. weekdays: 0=Mon..6=Sun (default every day).
            """
            return schedules().add(
                ScheduleCreate(
                    name=name, action=action, time_mode=time_mode, run_time=run_time,
                    offset_minutes=offset_minutes, target_type=target_type, target_id=target_id,
                    scene_id=scene_id, weekdays=weekdays if weekdays is not None else list(range(7)),
                    kind=kind,
                )
            )
