"""Compose and run the Luna Lumia MCP and HTTP server."""

from app.transport.branding import ServerBranding
from app.core import tenancy
from app.core.config import AppConfig
from app.data.database import Database
from app.transport.luna_mcp import LunaMCP
from app.integrations.devices import WizDiscovery, WizLightAdapter
from app.integrations.icue import ICueAdapter
from app.integrations.openrgb import OpenRGBAdapter
from app.integrations.router import LightRouter
from app.integrations.vibia import VibiaPlayback
from app.transport.http_routes import LumiaHTTPRoutes
from app.transport.mcp_tools import LumiaMCPTools
from app.services.playback import OwnerScenes, SceneEngine
from app.services.presets import PresetCatalog
from app.data.repositories import (
    CollectionRepository,
    LightRepository,
    LocationRepository,
    MusicAutomationRepository,
    MusicSchemeRepository,
    RoomImageRepository,
    SceneRepository,
    ScheduleRepository,
    TransitionRepository,
    WeatherAutomationRepository,
    WeatherRepository,
    WeatherSchemeRepository,
)
from app.services.application import (
    BackgroundImageService,
    CollectionService,
    LightControlService,
    LightService,
    LocationService,
    LumiaService,
    SceneService,
    ScheduleService,
    TransitionService,
    WeatherService,
)
from app.services.music import MusicService
from app.services.workers import MusicWorker, ScheduleWorker, WeatherWorker


class LunaLumiaApplication:
    """Compose and own the concrete Luna Lumia dependencies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.database = Database(config.database_url)
        self.database.open()
        self.database.initialize_schema()
        # Everyone starts with the built-in schemes; the owner's are refreshed on every start.
        self.database.tenants.after_create = PresetCatalog(
            SceneRepository(self.database),
            TransitionRepository(self.database),
            WeatherSchemeRepository(self.database),
            MusicSchemeRepository(self.database),
        ).install
        self.openrgb = OpenRGBAdapter(timeout=config.device_timeout_seconds)
        self.icue = ICueAdapter(config.icue_token, config.device_timeout_seconds, config.icue_host_tokens)
        self.adapter = LightRouter(
            WizLightAdapter(timeout=config.device_timeout_seconds), self.openrgb, self.icue
        )
        self.engine = SceneEngine(self.adapter.apply)
        self.engine.start()
        self.scenes = OwnerScenes(self.engine)
        self.service = self._build_service()
        self.branding = ServerBranding(config.mcp_public_url)
        self.mcp = LunaMCP(
            "LunaLumia",
            public_url=config.mcp_public_url or f"http://localhost:{config.port}",
            api_token=config.api_token,
            icons=self.branding.mcp_icons(),
            host=config.host,
            port=config.port,
            stateless_http=True,
            json_response=True,
        )
        LumiaMCPTools(self.mcp, self.service)
        LumiaHTTPRoutes(self.mcp, self.service, self.branding, config.api_token)
        self.workers = [
            ScheduleWorker(
                self.service.schedules, config.timezone, config.schedule_interval_seconds
            ),
            WeatherWorker(
                self.service.weather, config.timezone, config.schedule_interval_seconds, self.service.music
            ),
            MusicWorker(self.service.music, config.music_interval_seconds),
        ]
        for worker in self.workers:
            worker.start()

    def _build_service(self) -> LumiaService:
        lights = LightRepository(self.database)
        collections = CollectionRepository(self.database)
        images = BackgroundImageService(RoomImageRepository(self.database), lights, collections)
        control = LightControlService(lights, self.adapter, self.scenes)
        transitions = TransitionService(TransitionRepository(self.database))
        scenes = SceneService(SceneRepository(self.database), transitions, control, self.scenes)
        location = LocationService(LocationRepository(self.database), self.config.timezone)
        weather = WeatherService(
            WeatherRepository(self.database),
            WeatherSchemeRepository(self.database),
            WeatherAutomationRepository(self.database),
            scenes,
            location,
        )
        return LumiaService(
            lights=LightService(lights, WizDiscovery(), images, self.openrgb, self.icue),
            collections=CollectionService(collections, images),
            images=images,
            control=control,
            scenes=scenes,
            transitions=transitions,
            schedules=ScheduleService(ScheduleRepository(self.database), control, scenes, location),
            weather=weather,
            music=MusicService(
                VibiaPlayback(self.config.vibia_api_url, self.config.vibia_api_token),
                MusicSchemeRepository(self.database),
                MusicAutomationRepository(self.database),
                scenes,
                weather,
            ),
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
