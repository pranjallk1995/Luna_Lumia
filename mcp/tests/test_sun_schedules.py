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
    def pending(self, today, weekday):
        return [r for r in self.rows if r.get("run_date") == today or (not r.get("run_date") and weekday in r["weekdays"])]
    def add(self, entry, last_run_date=None): self.added.append((entry, last_run_date)); return {"id": 1}
    def update(self, schedule_id, entry, last_run_date=None):
        return {"id": schedule_id, "last_run_date": last_run_date} if schedule_id == 7 else None
    def get(self, schedule_id): return next((r for r in self.rows if r["id"] == schedule_id), None)
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

    def test_update_reports_a_missing_schedule(self):
        from app.core.errors import NotFoundError
        entry = ScheduleCreate(name="Wake", action="on", run_time="07:00")
        self.assertEqual(service().update(7, entry)["id"], 7)
        with self.assertRaises(NotFoundError):
            service().update(99, entry)
        with self.assertRaises(NotFoundError):
            service().get(99)

    def test_update_to_sunset_needs_a_saved_location(self):
        entry = ScheduleCreate(name="Dusk", action="on", time_mode="sunset")
        with self.assertRaisesRegex(ValueError, "Set your location"):
            service(location=None).update(7, entry)

    def test_time_mode_requires_a_time_and_sun_mode_drops_it(self):
        with self.assertRaises(ValueError):
            ScheduleCreate(name="Wake", action="on", time_mode="time")
        entry = ScheduleCreate(name="Dusk", action="on", time_mode="sunset", run_time="07:00", offset_minutes=-15)
        self.assertEqual((entry.run_time, entry.offset_minutes), (None, -15))

    def test_one_time_schedule_runs_only_on_its_date(self):
        ran = []
        scheduler = service(rows=[row(run_date=date(2026, 10, 20), weekdays=[1])])

        async def execute(schedule): ran.append(schedule["id"])
        scheduler.execute = execute
        scheduler.run_due(datetime(2026, 10, 27, 8, 0, tzinfo=IST))  # a later Tuesday
        self.assertEqual(ran, [])
        scheduler.run_due(datetime(2026, 10, 20, 8, 0, tzinfo=IST))
        self.assertEqual(ran, [7])

    def test_one_time_date_sets_its_weekday(self):
        entry = ScheduleCreate(name="Party", action="on", run_time="19:00", run_date="2026-11-07", weekdays=[0, 1])
        self.assertEqual((entry.run_date, entry.weekdays), (date(2026, 11, 7), [5]))

    def test_one_time_schedule_must_be_ahead_unless_switched_off(self):
        past = ScheduleCreate(name="Party", action="on", run_time="19:00", run_date="2020-01-01")
        with self.assertRaisesRegex(ValueError, "already passed"):
            service().add(past)
        service().add(past.model_copy(update={"enabled": False}))
        future = ScheduleCreate(name="Party", action="on", run_time="19:00", run_date="2099-01-01")
        scheduler = service()
        scheduler.add(future)
        self.assertEqual(scheduler.schedules.added[0][1], None)

    def test_location_today_reports_sun_times(self):
        today = LocationService(FakeLocations(BENGALURU), IST).today()
        self.assertEqual(today["name"], "Bengaluru")
        self.assertRegex(today["sunrise"], r"^0[5-7]:\d\d$")
        self.assertRegex(today["sunset"], r"^1[7-9]:\d\d$")


if __name__ == "__main__":
    unittest.main()
