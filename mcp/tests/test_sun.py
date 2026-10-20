import unittest
from datetime import date
from zoneinfo import ZoneInfo

from app.services.sun import SunCalculator

IST = ZoneInfo("Asia/Kolkata")


def minutes(moment):
    return moment.hour * 60 + moment.minute


class SunCalculatorTests(unittest.TestCase):
    """Reference times are published almanac values; NOAA's method is within a few minutes."""

    def assertNear(self, moment, hhmm, tolerance=4):
        hours, mins = map(int, hhmm.split(":"))
        self.assertLessEqual(abs(minutes(moment) - (hours * 60 + mins)), tolerance, f"{moment:%H:%M} vs {hhmm}")

    def test_new_delhi_summer_solstice(self):
        times = SunCalculator.times(date(2026, 6, 21), 28.61, 77.21, IST)
        self.assertNear(times["sunrise"], "05:24")
        self.assertNear(times["sunset"], "19:22")

    def test_bengaluru_october(self):
        times = SunCalculator.times(date(2026, 10, 19), 12.97, 77.59, IST)
        self.assertNear(times["sunrise"], "06:07")
        self.assertNear(times["sunset"], "17:58")

    def test_far_east_zone_keeps_the_requested_day(self):
        tokyo = ZoneInfo("Asia/Tokyo")
        times = SunCalculator.times(date(2026, 3, 20), 35.68, 139.69, tokyo)
        self.assertEqual(times["sunrise"].date(), date(2026, 3, 20))
        self.assertNear(times["sunrise"], "05:45")

    def test_polar_night_has_no_sunrise(self):
        times = SunCalculator.times(date(2026, 12, 21), 69.65, 18.96, ZoneInfo("Europe/Oslo"))
        self.assertIsNone(times["sunrise"])
        self.assertIsNone(times["sunset"])


if __name__ == "__main__":
    unittest.main()
