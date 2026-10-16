import asyncio
import threading
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .database import Database
from .devices import LightController, WizDiscovery
from .models import GroupCreate, LightCreate, LightState, LightUpdate, SceneCreate, ScheduleCreate
from .repository import LumiaRepository
from .services import LumiaService


class Scheduler:
    def __init__(self, service: LumiaService):
        self.service = service
        self.stop_event = threading.Event()

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="lumia-scheduler").start()

    def run(self):
        while not self.stop_event.wait(20):
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            try:
                for item in self.service.repository.due_schedules(now.date(), now.weekday(), now.time()):
                    if item["action"] == "scene": asyncio.run(self.service.apply_scene(item["target_type"], item["target_id"], item["scene_id"]))
                    else: asyncio.run(self.service.control(item["target_type"], item["target_id"], LightState(on=item["action"] == "on")))
                    self.service.repository.mark_ran(item["id"], now.date())
            except Exception:
                continue


class LumiaMCPAdapter:
    def __init__(self, server, service):
        self.server, self.service = server, service
        self.register()

    def register(self):
        repository, service, server = self.service.repository, self.service, self.server

        @server.tool()
        def list_lights():
            """List configured Luna Lumia lights and their last known states."""
            return repository.list_lights()

        @server.tool()
        async def discover_lights_on_network(broadcast_space: str = "255.255.255.255"):
            """Scan the local network for WiZ-compatible smart lights."""
            return await service.discover(broadcast_space)

        @server.tool()
        async def set_light(light_id: int, on: bool | None = None, brightness: int | None = None, color: str | None = None):
            """Control one light by id. Color is a #RRGGBB value."""
            return await service.control("light", light_id, LightState(on=on, brightness=brightness, color=color))

        @server.tool()
        async def set_all_lights(on: bool):
            """Turn all configured lights on or off."""
            return await service.control("all", None, LightState(on=on))

        @server.tool()
        async def set_group(group_id: int, on: bool | None = None, brightness: int | None = None, color: str | None = None):
            """Control every light in a saved group."""
            return await service.control("group", group_id, LightState(on=on, brightness=brightness, color=color))

        @server.tool()
        async def activate_scene(scene_id: int, target_type: str = "all", target_id: int | None = None):
            """Apply a saved dynamic color scheme to all lights, one light, or a group."""
            return await service.apply_scene(target_type, target_id, scene_id)


class LumiaHTTPAdapter:
    def __init__(self, server, service): self.server, self.service = server, service; self.register()
    @classmethod
    def json_value(cls, value):
        if isinstance(value, BaseModel): return cls.json_value(value.model_dump())
        if isinstance(value, dict): return {k: cls.json_value(v) for k,v in value.items()}
        if isinstance(value, (list,tuple)): return [cls.json_value(v) for v in value]
        if isinstance(value, Decimal): return float(value)
        if hasattr(value, "isoformat"): return value.isoformat()
        return value
    @classmethod
    def response(cls, value, status=200): return JSONResponse(cls.json_value(value), status_code=status)
    @classmethod
    def error(cls, error):
        if isinstance(error, ValidationError): return cls.response({"error":"Invalid request","details":error.errors()},422)
        if isinstance(error, (ValueError, TypeError)): return cls.response({"error":str(error)},400)
        return cls.response({"error":str(error)},500)
    @staticmethod
    async def payload(request, model): return model.model_validate(await request.json())

    def register(self):
        server, service, repo = self.server, self.service, self.service.repository
        @server.custom_route("/health", methods=["GET"])
        async def health(request): del request; return self.response({"status":"ok","service":"luna-lumia"})

        @server.custom_route("/api/dashboard", methods=["GET"])
        async def dashboard(request):
            del request
            return self.response({"lights":repo.list_lights(),"groups":repo.list_groups(),"scenes":repo.list_scenes(),"schedules":repo.list_schedules()})

        @server.custom_route("/api/discovery", methods=["POST"])
        async def discovery(request):
            try:
                body = await request.json()
                return self.response(await service.discover(body.get("broadcast_space", "255.255.255.255")))
            except Exception as e:
                return self.error(e)

        @server.custom_route("/api/lights", methods=["POST"])
        async def add_light(request):
            try: return self.response(repo.add_light(await self.payload(request,LightCreate)),201)
            except Exception as e: return self.error(e)
        @server.custom_route("/api/lights/{item_id}", methods=["DELETE"])
        async def delete_light(request): return Response(status_code=204) if repo.delete_light(int(request.path_params["item_id"])) else self.response({"error":"Not found"},404)

        @server.custom_route("/api/lights/{item_id}", methods=["PUT"])
        async def rename_light(request):
            try:
                entry = await self.payload(request, LightUpdate)
                result = repo.rename_light(int(request.path_params["item_id"]), entry.name)
                return self.response(result) if result else self.response({"error":"Not found"},404)
            except Exception as e:
                return self.error(e)

        @server.custom_route("/api/control/{target_type}", methods=["POST"])
        async def control(request):
            try:
                body=await request.json(); state=LightState.model_validate(body.get("state",body))
                return self.response(await service.control(request.path_params["target_type"],body.get("target_id"),state))
            except Exception as e: return self.error(e)
        @server.custom_route("/api/scenes/{item_id}/apply", methods=["POST"])
        async def apply_scene(request):
            try:
                body=await request.json(); return self.response(await service.apply_scene(body.get("target_type","all"),body.get("target_id"),int(request.path_params["item_id"])))
            except Exception as e: return self.error(e)

        def crud(path, model, add, delete):
            @server.custom_route(path, methods=["POST"])
            async def create(request):
                try: return self.response(add(await self.payload(request,model)),201)
                except Exception as e: return self.error(e)
            @server.custom_route(path+"/{item_id}", methods=["DELETE"])
            async def remove(request): return Response(status_code=204) if delete(int(request.path_params["item_id"])) else self.response({"error":"Not found"},404)
        crud("/api/groups",GroupCreate,repo.add_group,repo.delete_group)
        crud("/api/scenes",SceneCreate,repo.add_scene,repo.delete_scene)
        crud("/api/schedules",ScheduleCreate,repo.add_schedule,repo.delete_schedule)


class LunaLumiaApplication:
    def __init__(self):
        self.database=Database.from_env(); self.database.open()
        self.repository=LumiaRepository(self.database); self.repository.ensure_schema()
        self.service=LumiaService(
            self.repository,
            LightController(self.repository),
            WizDiscovery(),
        )
        self.mcp=FastMCP("LunaLumia",host="0.0.0.0",port=8000,stateless_http=True,json_response=True)
        self.mcp_adapter=LumiaMCPAdapter(self.mcp,self.service); self.http_adapter=LumiaHTTPAdapter(self.mcp,self.service)
        self.scheduler=Scheduler(self.service); self.scheduler.start()
    def run(self):
        try: self.mcp.run(transport="streamable-http")
        finally: self.scheduler.stop_event.set(); self.database.close()


application=LunaLumiaApplication()
mcp=application.mcp
app=mcp.streamable_http_app()
if __name__ == "__main__": application.run()
