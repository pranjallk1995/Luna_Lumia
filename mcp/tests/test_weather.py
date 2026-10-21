import asyncio
import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.core.models import WeatherAutomationUpdate, WeatherReport, WeatherSlot
from app.services.application import LocationService, WeatherService
from app.services.presets import WEATHER_SEQUENCES, WEATHER_SOLIDS, WeatherPresets
from app.transport.mcp_tools import LumiaMCPTools

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 19)  # Bengaluru: sunrise about 06:07, sunset about 17:58


def at(hour, minute=0):
    return datetime(2026, 10, 19, hour, minute, tzinfo=IST)


class FakeLocations:
    def __init__(self, location=None): self.location = location
    def get(self): return self.location


class FakeDays:
    def __init__(self): self.reports = {}

    def get(self, day): return self.reports.get(day)

    def save(self, report):
        row = {
            "day": report.day.isoformat(), "location": report.location, "summary": report.summary,
            "source": report.source, "periods": [p.model_dump(mode="json") for p in report.periods],
        }
        self.reports[report.day] = row
        return row

    def delete(self, day): return self.reports.pop(day, None) is not None


class FakeSlots:
    def __init__(self, scenes): self.scenes, self.rows = scenes, {}

    def list(self):
        names = {scene["id"]: scene for scene in self.scenes.rows}
        return [
            {"condition": c, "daypart": d, "scene_id": scene_id,
             "scheme_name": names[scene_id]["name"] if scene_id else None,
             "scheme_kind": names[scene_id]["kind"] if scene_id else None}
            for (c, d), scene_id in self.rows.items()
        ]

    def set(self, condition, daypart, scene_id): self.rows[(condition, daypart)] = scene_id


class FakeAutomation:
    def __init__(self): self.row = {"enabled": False, "target_type": "on", "target_id": None, "last_applied": None}
    def get(self): return dict(self.row)

    def save(self, entry):
        self.row = {**entry.model_dump(), "last_applied": None}
        return dict(self.row)

    def mark_applied(self, key): self.row["last_applied"] = key


class FakeSceneRepository:
    """Every built-in weather scheme plus one user scheme (id 100)."""

    def __init__(self):
        names = [name for name, *_ in WEATHER_SOLIDS] + list(WEATHER_SEQUENCES)
        self.rows = [{"id": i, "name": n, "kind": "solid", "is_preset": True} for i, n in enumerate(names, 1)]
        self.rows.append({"id": 100, "name": "My rain", "kind": "sequence", "is_preset": False})

    def list(self): return self.rows


class FakeScenes:
    def __init__(self):
        self.scenes = FakeSceneRepository()
        self.applied = []

    def get(self, scene_id):
        if scene_id not in {row["id"] for row in self.scenes.rows}:
            raise LookupError("Scene not found")
        return {"id": scene_id}

    async def apply(self, target_type, target_id, scene_id):
        self.applied.append((target_type, target_id, scene_id))
        return {"scene": scene_id, "target_type": target_type}


def weather_service(location={"name": "Bengaluru", "latitude": 12.97, "longitude": 77.59}):
    scenes = FakeScenes()
    return WeatherService(
        FakeDays(), FakeSlots(scenes.scenes), FakeAutomation(), scenes,
        LocationService(FakeLocations(location), IST),
    )


def report(*periods):
    return WeatherReport(day=DAY, periods=[{"start": s, "condition": c} for s, c in periods])


class WeatherModelTests(unittest.TestCase):
    def test_forecast_words_map_to_conditions_and_periods_are_sorted(self):
        entry = report(("18:00", "Light rain"), ("06:00", "sunny"), ("12:00", "Overcast"))
        self.assertEqual([p.condition for p in entry.periods], ["clear", "cloudy", "rain"])
        self.assertEqual(entry.periods[0].start, time(6, 0))

    def test_unknown_condition_and_duplicate_starts_are_rejected(self):
        with self.assertRaises(ValidationError):
            report(("06:00", "volcanic"))
        with self.assertRaises(ValidationError):
            report(("06:00", "clear"), ("06:00", "rain"))

    def test_slot_and_automation_validation(self):
        self.assertEqual(WeatherSlot(condition="storm", daypart="night").condition, "thunderstorm")
        with self.assertRaises(ValidationError):
            WeatherSlot(condition="rain", daypart="evening")
        with self.assertRaises(ValidationError):
            WeatherAutomationUpdate(enabled=True, target_type="group")


class WeatherPresetTests(unittest.TestCase):
    def test_every_slot_has_a_built_in_scheme(self):
        names = {name for name, *_ in WEATHER_SOLIDS} | set(WEATHER_SEQUENCES)
        slots = WeatherPresets.slots()
        self.assertEqual(len(slots), 14)
        self.assertEqual({WeatherPresets.name(c, d) for c, d in slots}, names)


class WeatherServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = weather_service()
        self.service.record(report(("00:00", "clear"), ("13:00", "rain"), ("20:00", "cloudy")))

    def test_period_and_daypart_follow_the_clock_and_the_sun(self):
        morning, evening = self.service.current(at(9)), self.service.current(at(18, 30))
        self.assertEqual((morning["condition"], morning["daypart"]), ("clear", "day"))
        self.assertEqual((evening["condition"], evening["daypart"]), ("rain", "night"))
        self.assertEqual(evening["scheme"]["name"], "Weather · Rain night")

    def test_without_a_location_day_is_six_to_six(self):
        service = weather_service(location=None)
        self.assertEqual(service.daypart(at(5, 59)), "night")
        self.assertEqual(service.daypart(at(17, 59)), "day")

    def test_no_report_means_no_current_weather(self):
        self.assertIsNone(weather_service().current(at(9)))
        with self.assertRaisesRegex(Exception, "No weather recorded"):
            asyncio.run(weather_service().apply_current(moment=at(9)))

    def test_update_period_changes_one_period_and_keeps_the_rest(self):
        self.service.update_period(DAY, "13:00", {"condition": "thunderstorm", "temperature_c": 24})
        self.service.update_period(DAY, "16:30", {"condition": "fog"})
        periods = self.service.get(DAY)["periods"]
        self.assertEqual([(p["start"], p["condition"]) for p in periods], [
            ("00:00:00", "clear"), ("13:00:00", "thunderstorm"), ("16:30:00", "fog"), ("20:00:00", "cloudy"),
        ])
        self.assertEqual(periods[1]["temperature_c"], 24)

    def test_assigned_scheme_replaces_the_built_in_until_reset(self):
        self.service.set_slot("rain", "night", 100)
        self.assertEqual(self.service.current(at(19))["scheme"]["name"], "My rain")
        decorated = self.service.decorate([{"id": 100}])
        self.assertEqual(decorated[0]["weather_slots"], ["rain/night"])
        self.service.reset_slots("rain")
        self.assertEqual(self.service.current(at(19))["scheme"]["name"], "Weather · Rain night")

    def test_unknown_scheme_cannot_be_assigned(self):
        with self.assertRaises(LookupError):
            self.service.set_slot("rain", "night", 999)

    def test_automation_applies_once_per_change(self):
        self.service.follow(at(9))
        self.assertEqual(self.service.scenes.applied, [])  # disabled
        self.service.set_automation(WeatherAutomationUpdate(enabled=True))
        self.service.follow(at(9))
        self.service.follow(at(10))
        self.service.follow(at(14))
        self.service.follow(at(18, 30))
        names = {row["id"]: row["name"] for row in self.service.scenes.scenes.rows}
        self.assertEqual(
            [(target, names[scene]) for target, _, scene in self.service.scenes.applied],
            [("on", "Weather · Clear day"), ("on", "Weather · Rain day"), ("on", "Weather · Rain night")],
        )


class FakeServer:
    def __init__(self): self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


class WeatherToolTests(unittest.TestCase):
    def setUp(self):
        self.weather = weather_service()
        self.weather.now = lambda: at(9)
        service = type("Service", (), {})()
        service.weather = self.weather
        for name in ("lights", "collections", "images", "control", "scenes", "transitions", "schedules"):
            setattr(service, name, object())
        self.server = FakeServer()
        LumiaMCPTools(self.server, service)

    def test_weather_tools_are_registered(self):
        expected = {
            "record_weather", "update_weather_period", "get_weather", "delete_weather",
            "list_weather_schemes", "set_weather_scheme", "reset_weather_schemes",
            "apply_weather_scheme", "set_weather_automation",
        }
        self.assertTrue(expected.issubset(self.server.tools))

    def test_record_then_get_and_apply_todays_weather(self):
        tools = self.server.tools
        tools["record_weather"]([{"start": "06:00", "condition": "partly sunny"}], day="2026-10-19")
        today = tools["get_weather"]()
        self.assertEqual(today["now"]["scheme"]["name"], "Weather · Partly cloudy day")
        result = asyncio.run(tools["apply_weather_scheme"]("group", 4))
        self.assertEqual(result["target_type"], "group")

    def test_update_period_ignores_fields_not_given(self):
        tools = self.server.tools
        tools["record_weather"]([{"start": "06:00", "condition": "clear", "humidity": 40}], day="2026-10-19")
        tools["update_weather_period"]("06:00", temperature_c=29.5, day="2026-10-19")
        period = tools["get_weather"]("2026-10-19")["periods"][0]
        self.assertEqual((period["condition"], period["humidity"], period["temperature_c"]), ("clear", 40, 29.5))

    def test_set_weather_scheme_accepts_forecast_words(self):
        slot = self.server.tools["set_weather_scheme"]("drizzle", "night", 100)
        self.assertEqual((slot["condition"], slot["scheme"]["id"], slot["is_built_in"]), ("rain", 100, False))


if __name__ == "__main__":
    unittest.main()
