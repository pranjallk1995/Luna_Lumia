"""Compose and run the Luna Lumia MCP and HTTP server."""

from mcp.server.fastmcp import FastMCP

from .config import AppConfig
from .database import Database
from .devices import WizDiscovery, WizLightAdapter
from .http_routes import LumiaHTTPRoutes
from .mcp_tools import LumiaMCPTools
from .repositories import (
    CollectionRepository,
    LightRepository,
    RoomImageRepository,
    SceneRepository,
    ScheduleRepository,
)
from .services import (
    BackgroundImageService,
    CollectionService,
    LightControlService,
    LightService,
    LumiaService,
    SceneService,
    ScheduleService,
)
from .workers import LightStatusPoller, ScheduleWorker


class LunaLumiaApplication:
    """Compose and own the concrete Luna Lumia dependencies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.database = Database(config.database_url)
        self.database.open()
        self.database.initialize_schema()
        self.service = self._build_service()
        self.mcp = FastMCP(
            "LunaLumia",
            host=config.host,
            port=config.port,
            stateless_http=True,
            json_response=True,
        )
        LumiaMCPTools(self.mcp, self.service)
        LumiaHTTPRoutes(self.mcp, self.service)
        self.workers = [
            ScheduleWorker(
                self.service.schedules, config.timezone, config.schedule_interval_seconds
            ),
            LightStatusPoller(self.service.control, config.status_poll_interval_seconds),
        ]
        for worker in self.workers:
            worker.start()

    def _build_service(self) -> LumiaService:
        lights = LightRepository(self.database)
        collections = CollectionRepository(self.database)
        images = BackgroundImageService(RoomImageRepository(self.database), lights, collections)
        control = LightControlService(
            lights, WizLightAdapter(timeout=self.config.device_timeout_seconds)
        )
        scenes = SceneService(SceneRepository(self.database), control)
        return LumiaService(
            lights=LightService(lights, WizDiscovery(), images),
            collections=CollectionService(collections, images),
            images=images,
            control=control,
            scenes=scenes,
            schedules=ScheduleService(ScheduleRepository(self.database), control, scenes),
        )

    def run(self) -> None:
        try:
            self.mcp.run(transport="streamable-http")
        finally:
            for worker in self.workers:
                worker.stop()
            self.database.close()


application = LunaLumiaApplication(AppConfig.from_env())
mcp = application.mcp
app = mcp.streamable_http_app()

if __name__ == "__main__":
    application.run()
