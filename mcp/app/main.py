"""Compose and run the Luna Lumia MCP and HTTP server."""

from mcp.server.fastmcp import FastMCP

from .branding import ServerBranding
from .config import AppConfig
from .database import Database
from .devices import WizDiscovery, WizLightAdapter
from .http_routes import LumiaHTTPRoutes
from .mcp_tools import LumiaMCPTools
from .playback import SceneEngine
from .presets import PresetCatalog
from .repositories import (
    CollectionRepository,
    LightRepository,
    RoomImageRepository,
    SceneRepository,
    ScheduleRepository,
    TransitionRepository,
)
from .services import (
    BackgroundImageService,
    CollectionService,
    LightControlService,
    LightService,
    LumiaService,
    SceneService,
    ScheduleService,
    TransitionService,
)
from .workers import ScheduleWorker


class LunaLumiaApplication:
    """Compose and own the concrete Luna Lumia dependencies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.database = Database(config.database_url)
        self.database.open()
        self.database.initialize_schema()
        PresetCatalog(SceneRepository(self.database), TransitionRepository(self.database)).install()
        self.adapter = WizLightAdapter(timeout=config.device_timeout_seconds)
        self.engine = SceneEngine(self.adapter.apply)
        self.engine.start()
        self.service = self._build_service()
        self.branding = ServerBranding()
        self.mcp = FastMCP(
            "LunaLumia",
            icons=self.branding.mcp_icons(),
            host=config.host,
            port=config.port,
            stateless_http=True,
            json_response=True,
        )
        LumiaMCPTools(self.mcp, self.service)
        LumiaHTTPRoutes(self.mcp, self.service, self.branding)
        self.workers = [
            ScheduleWorker(
                self.service.schedules, config.timezone, config.schedule_interval_seconds
            ),
        ]
        for worker in self.workers:
            worker.start()

    def _build_service(self) -> LumiaService:
        lights = LightRepository(self.database)
        collections = CollectionRepository(self.database)
        images = BackgroundImageService(RoomImageRepository(self.database), lights, collections)
        control = LightControlService(lights, self.adapter, self.engine)
        transitions = TransitionService(TransitionRepository(self.database))
        scenes = SceneService(SceneRepository(self.database), transitions, control, self.engine)
        return LumiaService(
            lights=LightService(lights, WizDiscovery(), images),
            collections=CollectionService(collections, images),
            images=images,
            control=control,
            scenes=scenes,
            transitions=transitions,
            schedules=ScheduleService(ScheduleRepository(self.database), control, scenes),
        )

    def run(self) -> None:
        try:
            self.mcp.run(transport="streamable-http")
        finally:
            for worker in self.workers:
                worker.stop()
            self.engine.close()
            self.database.close()


application = LunaLumiaApplication(AppConfig.from_env())
mcp = application.mcp
app = mcp.streamable_http_app()

if __name__ == "__main__":
    application.run()
