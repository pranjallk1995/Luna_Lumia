"""REST routes used by the Luna Lumia Streamlit dashboard."""

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app.transport.auth import APIAuthenticator
from app.integrations.devices import GLOBAL_BROADCAST
from app.transport.branding import ServerBranding
from app.core.errors import NotFoundError
from app.core.models import (
    GroupCreate,
    GroupMembersUpdate,
    GroupUpdate,
    LightCreate,
    LightImageUpdate,
    LightState,
    LightUpdate,
    LocationUpdate,
    RoomImageUpdate,
    SceneCreate,
    ScheduleCreate,
    TransitionCreate,
)
from app.services.application import LumiaService

Handler = Callable[[Request], Awaitable[Any]]
NO_CONTENT = 204


class LumiaHTTPRoutes:
    """Translate HTTP requests into service calls and results into JSON."""

    def __init__(
        self, server: FastMCP, service: LumiaService, branding: ServerBranding, api_token: str
    ) -> None:
        self.server = server
        self.service = service
        self.branding = branding
        self.authenticator = APIAuthenticator(api_token)
        self._register()

    @classmethod
    def json_value(cls, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return cls.json_value(value.model_dump())
        if isinstance(value, BaseException):
            return str(value)
        if isinstance(value, dict):
            return {key: cls.json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls.json_value(item) for item in value]
        if isinstance(value, Decimal):
            return float(value)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    @classmethod
    def response(cls, value: Any, status: int = 200) -> Response:
        if isinstance(value, Response):
            return value
        if status == NO_CONTENT:
            return Response(status_code=NO_CONTENT)
        return JSONResponse(cls.json_value(value), status_code=status)

    @classmethod
    def error(cls, error: Exception) -> Response:
        if isinstance(error, ValidationError):
            return cls.response({"error": "Invalid request", "details": error.errors()}, 422)
        if isinstance(error, (NotFoundError, FileNotFoundError)):
            return cls.response({"error": str(error) or "Not found"}, 404)
        if isinstance(error, (ValueError, TypeError)):
            return cls.response({"error": str(error)}, 400)
        return cls.response({"error": str(error)}, 500)

    @staticmethod
    async def payload(request: Request, model: type[BaseModel]) -> Any:
        return model.model_validate(await request.json())

    @staticmethod
    def path_id(request: Request, name: str = "item_id") -> int:
        return int(request.path_params[name])

    def route(self, method: str, path: str, handler: Handler, status: int = 200) -> None:
        """Register ``handler`` with uniform error translation."""

        async def endpoint(request: Request) -> Response:
            if path.startswith("/api/"):
                rejection = self.authenticator.rejection(request)
                if rejection is not None:
                    return rejection
            try:
                return self.response(await handler(request), status)
            except Exception as error:
                return self.error(error)

        self.server.custom_route(path, methods=[method])(endpoint)

    ICON_HEADERS = {
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
    }

    def _register_icons(self) -> None:
        """Favicon and PNG icons for MCP connector clients that fetch them by URL."""
        branding = self.branding

        async def favicon(request: Request):
            return FileResponse(
                branding.favicon_path(), media_type="image/x-icon", headers=self.ICON_HEADERS
            )

        async def icon(request: Request):
            return FileResponse(
                branding.icon_path(request.path_params["name"]),
                media_type="image/png",
                headers=self.ICON_HEADERS,
            )

        async def home(request: Request):
            return HTMLResponse(branding.home_page(), headers=self.ICON_HEADERS)

        self.route("GET", "/", home)
        self.route("GET", "/favicon.ico", favicon)
        self.route("GET", "/icons/{name}", icon)

    def _register(self) -> None:
        self.route("GET", "/health", self.health)
        self._register_icons()
        self.route("GET", "/api/dashboard", self.dashboard)
        self.route("POST", "/api/discovery", self.discover)
        self._register_lights()
        self._register_collections("room")
        self._register_collections("group")
        self._register_scenes()
        self._register_schedules()
        self.route("PUT", "/api/room-image", self.update_room_image)
        self.route("POST", "/api/control/{target_type}", self.control)

    async def health(self, request: Request) -> dict:
        return {"status": "ok", "service": "luna-lumia"}

    async def dashboard(self, request: Request) -> dict:
        return self.service.dashboard()

    async def discover(self, request: Request) -> list[dict]:
        body = await request.json()
        return await self.service.lights.discover(body.get("broadcast_space", GLOBAL_BROADCAST))

    async def update_room_image(self, request: Request) -> Any:
        entry = await self.payload(request, RoomImageUpdate)
        return self.service.images.update_room_image(entry.room_key, entry.image_url)

    async def control(self, request: Request) -> list[dict]:
        body = await request.json()
        state = LightState.model_validate(body.get("state", body))
        return await self.service.control.control(
            request.path_params["target_type"], body.get("target_id"), state
        )

    def _register_lights(self) -> None:
        lights, images = self.service.lights, self.service.images

        async def add(request: Request):
            return lights.add(await self.payload(request, LightCreate))

        async def rename(request: Request):
            entry = await self.payload(request, LightUpdate)
            return lights.rename(self.path_id(request), entry.name)

        async def delete(request: Request):
            lights.delete(self.path_id(request))

        async def background(request: Request):
            entry = await self.payload(request, LightImageUpdate)
            return images.apply_light_image(self.path_id(request), entry.image_url)

        self.route("POST", "/api/lights", add, 201)
        self.route("PUT", "/api/lights/{item_id}", rename)
        self.route("DELETE", "/api/lights/{item_id}", delete, NO_CONTENT)
        self.route("PUT", "/api/lights/{item_id}/background", background)

        async def refresh(request: Request):
            return await self.service.refresh_lights()

        self.route("POST", "/api/lights/refresh", refresh)

    def _register_collections(self, kind: str) -> None:
        collections, images = self.service.collections, self.service.images
        base = f"/api/{kind}s"

        async def create(request: Request):
            return collections.create(await self.payload(request, GroupCreate), kind)

        async def rename(request: Request):
            entry = await self.payload(request, GroupUpdate)
            return collections.rename(self.path_id(request), kind, entry.name)

        async def delete(request: Request):
            collections.delete(self.path_id(request), kind)

        async def add_lights(request: Request):
            entry = await self.payload(request, GroupMembersUpdate)
            return collections.add_members(self.path_id(request), kind, entry.light_ids)

        async def remove_light(request: Request):
            collections.remove_member(
                self.path_id(request), kind, self.path_id(request, "light_id")
            )

        async def background(request: Request):
            entry = await self.payload(request, LightImageUpdate)
            return images.apply_collection_image(self.path_id(request), entry.image_url)

        self.route("POST", base, create, 201)
        self.route("PUT", f"{base}/{{item_id}}", rename)
        self.route("DELETE", f"{base}/{{item_id}}", delete, NO_CONTENT)
        self.route("POST", f"{base}/{{item_id}}/lights", add_lights)
        self.route("DELETE", f"{base}/{{item_id}}/lights/{{light_id}}", remove_light, NO_CONTENT)
        self.route("PUT", f"{base}/{{item_id}}/background", background)

    def _register_scenes(self) -> None:
        scenes = self.service.scenes

        async def create(request: Request):
            return scenes.add(await self.payload(request, SceneCreate))

        async def delete(request: Request):
            scenes.delete(self.path_id(request))

        async def apply(request: Request):
            body = await request.json()
            return await scenes.apply(
                body.get("target_type", "all"), body.get("target_id"), self.path_id(request)
            )

        self.route("POST", "/api/scenes", create, 201)
        self.route("DELETE", "/api/scenes/{item_id}", delete, NO_CONTENT)
        self.route("POST", "/api/scenes/{item_id}/apply", apply)

        async def stop(request: Request):
            body = await request.json()
            return scenes.stop(body.get("target_type", "all"), body.get("target_id"))

        self.route("POST", "/api/scenes/stop", stop)

        async def update(request: Request):
            return scenes.update(self.path_id(request), await self.payload(request, SceneCreate))

        self.route("PUT", "/api/scenes/{item_id}", update)

        transitions = self.service.transitions

        async def create_transition(request: Request):
            return transitions.add(await self.payload(request, TransitionCreate))

        async def delete_transition(request: Request):
            transitions.delete(self.path_id(request))

        self.route("POST", "/api/transitions", create_transition, 201)
        self.route("DELETE", "/api/transitions/{item_id}", delete_transition, NO_CONTENT)

        async def update_transition(request: Request):
            return transitions.update(self.path_id(request), await self.payload(request, TransitionCreate))

        self.route("PUT", "/api/transitions/{item_id}", update_transition)

    def _register_schedules(self) -> None:
        schedules = self.service.schedules

        async def create(request: Request):
            return schedules.add(await self.payload(request, ScheduleCreate))

        async def update(request: Request):
            return schedules.update(self.path_id(request), await self.payload(request, ScheduleCreate))

        async def delete(request: Request):
            schedules.delete(self.path_id(request))

        async def save_location(request: Request):
            schedules.location.save(await self.payload(request, LocationUpdate))
            return schedules.location.today()

        self.route("PUT", "/api/location", save_location)
        self.route("POST", "/api/schedules", create, 201)
        self.route("DELETE", "/api/schedules/{item_id}", delete, NO_CONTENT)
        self.route("PUT", "/api/schedules/{item_id}", update)
