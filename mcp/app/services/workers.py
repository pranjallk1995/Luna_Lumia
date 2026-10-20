"""Background threads that run due schedules."""

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.application import ScheduleService


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
