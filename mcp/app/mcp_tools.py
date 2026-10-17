"""MCP tools that let LLM clients manage Luna Lumia lights."""

from mcp.server.fastmcp import FastMCP

from .devices import GLOBAL_BROADCAST
from .models import GroupCreate, LightImageUpdate, LightState, RoomImageUpdate
from .services import LumiaService


class LumiaMCPTools:
    """Register Luna Lumia's MCP tool surface on a FastMCP server."""

    def __init__(self, server: FastMCP, service: LumiaService) -> None:
        self.server = server
        self.service = service
        self._register_inventory_tools()
        self._register_image_tools()
        self._register_control_tools()

    def _register_inventory_tools(self) -> None:
        server, lights, collections = self.server, self.service.lights, self.service.collections

        @server.tool()
        def list_lights():
            """List configured Luna Lumia lights and their last known states."""
            return lights.list()

        @server.tool()
        def create_room(name: str, light_ids: list[int]):
            """Create a room. A light can belong to only one room."""
            return collections.create(GroupCreate(name=name, light_ids=light_ids), "room")

        @server.tool()
        def create_group(name: str, light_ids: list[int]):
            """Create a reusable group. Lights may belong to multiple groups."""
            return collections.create(GroupCreate(name=name, light_ids=light_ids), "group")

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

    def _register_control_tools(self) -> None:
        server, control, scenes = self.server, self.service.control, self.service.scenes

        @server.tool()
        async def set_light(
            light_id: int,
            on: bool | None = None,
            brightness: int | None = None,
            color: str | None = None,
        ):
            """Control one light by id. Color is a #RRGGBB value."""
            state = LightState(on=on, brightness=brightness, color=color)
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
        ):
            """Control every light in a saved group."""
            state = LightState(on=on, brightness=brightness, color=color)
            return await control.control("group", group_id, state)

        @server.tool()
        async def activate_scene(scene_id: int, target_type: str = "all", target_id: int | None = None):
            """Apply a saved dynamic color scheme to all lights, one light, or a group."""
            return await scenes.apply(target_type, target_id, scene_id)
