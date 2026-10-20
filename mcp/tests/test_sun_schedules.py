import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.core.models import ScheduleCreate
from app.services.application import LocationService, ScheduleService

IST = ZoneInfo("Asia/Kolkata")
BENGALURU = {"name": "Bengaluru", "latitude": 12.97, "longitude": 77.59}


class FakeLocations:
    def __init__(self, location=None): self.location = location
    def get(self): return self.location


class FakeSchedules:
    def __init__(self, rows=()): self.rows, self.added, self.ran = list(rows), [], []
    def pending(self, today, weekday): return [r for r in self.rows if weekday in r["weekdays"]]
    def add(self, entry, last_run_date=None): self.added.append((entry, last_run_date)); return {"id": 1}
    def mark_ran(self, schedule_id, day): self.ran.append(schedule_id)
    def list(self): return self.rows


def service(location=BENGALURU, rows=()):
    return ScheduleService(FakeSchedules(rows), None, None, LocationService(FakeLocations(location), IST))


def row(**values):
    return {"id": 7, "time_mode": "time", "run_time": "07:00:00", "offset_minutes": 0,
            "weekdays": list(range(7)), "target_type": "all", "target_id": None, "action": "on", **values}


class SunScheduleTests(unittest.TestCase):
    DAY = date(2026, 10, 19)  # Bengaluru sunset is about 17:58

    def test_sunset_with_offset_resolves_to_that_days_time(self):
        at = service().time_on(row(time_mode="sunset", offset_minutes=-30), self.DAY)
        self.assertTrue(time(17, 23) <= at <= time(17, 33), at)

    def test_sun_schedule_without_location_never_runs(self):
        self.assertIsNone(service(location=None).time_on(row(time_mode="sunrise"), self.DAY))

    def test_run_due_waits_until_the_resolved_time(self):
        ran = []
        scheduler = service(rows=[row(time_mode="sunset")])

        async def execute(schedule): ran.append(schedule["id"])
        scheduler.execute = execute
        scheduler.run_due(datetime(2026, 10, 19, 17, 0, tzinfo=IST))
        self.assertEqual(ran, [])
        scheduler.run_due(datetime(2026, 10, 19, 18, 10, tzinfo=IST))
        self.assertEqual(ran, [7])

    def test_sun_schedule_needs_a_saved_location(self):
        entry = ScheduleCreate(name="Dusk", action="on", time_mode="sunset")
        with self.assertRaisesRegex(ValueError, "Set your location"):
            service(location=None).add(entry)

    def test_time_mode_requires_a_time_and_sun_mode_drops_it(self):
        with self.assertRaises(ValueError):
            ScheduleCreate(name="Wake", action="on", time_mode="time")
        entry = ScheduleCreate(name="Dusk", action="on", time_mode="sunset", run_time="07:00", offset_minutes=-15)
        self.assertEqual((entry.run_time, entry.offset_minutes), (None, -15))

    def test_location_today_reports_sun_times(self):
        today = LocationService(FakeLocations(BENGALURU), IST).today()
        self.assertEqual(today["name"], "Bengaluru")
        self.assertRegex(today["sunrise"], r"^0[5-7]:\d\d$")
        self.assertRegex(today["sunset"], r"^1[7-9]:\d\d$")


if __name__ == "__main__":
    unittest.main()
