"""Background threads that run due schedules and follow the weather and the music."""

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.application import ScheduleService, WeatherService
from app.services.music import MusicService


class PeriodicWorker:
    """Run ``tick`` on a daemon thread every ``interval`` seconds until stopped."""

    name = "lumia-worker"

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.stop_event = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self.run, daemon=True, name=self.name).start()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        while not self.stop_event.wait(self.interval):
            try:
                self.tick()
            except Exception:
                continue

    def tick(self) -> None:
        raise NotImplementedError


class ScheduleWorker(PeriodicWorker):
    name = "lumia-scheduler"

    def __init__(self, schedules: ScheduleService, timezone: ZoneInfo, interval: float) -> None:
        super().__init__(interval)
        self.schedules = schedules
        self.timezone = timezone

    def tick(self) -> None:
        self.schedules.run_due(datetime.now(self.timezone))


class WeatherWorker(PeriodicWorker):
    name = "lumia-weather"

    def __init__(
        self, weather: WeatherService, timezone: ZoneInfo, interval: float, music: MusicService | None = None
    ) -> None:
        super().__init__(interval)
        self.weather = weather
        self.timezone = timezone
        self.music = music

    def tick(self) -> None:
        # While music automation lights the room for a playing track, the weather waits.
        if self.music is not None and self.music.holds_lights():
            return
        self.weather.follow(datetime.now(self.timezone))


class MusicWorker(PeriodicWorker):
    name = "lumia-music"

    def __init__(self, music: MusicService, interval: float) -> None:
        super().__init__(interval)
        self.music = music

    def tick(self) -> None:
        self.music.follow()
