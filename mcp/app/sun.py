"""Sunrise and sunset times from latitude and longitude, computed locally.

Uses the NOAA sunrise equation (accurate to about a minute away from the
poles), so no network service is needed.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


class SunCalculator:
    """Times of sunrise and sunset; ``None`` when the sun does not rise or set that day."""

    ZENITH = 90.833  # official sunrise/sunset: sun's upper limb at the horizon, with refraction

    @classmethod
    def _utc_hours(cls, day: date, latitude: float, longitude: float, rising: bool) -> float | None:
        rad, deg = math.radians, math.degrees
        lng_hour = longitude / 15
        t = day.timetuple().tm_yday + ((6 if rising else 18) - lng_hour) / 24
        mean_anomaly = 0.9856 * t - 3.289
        true_longitude = (
            mean_anomaly
            + 1.916 * math.sin(rad(mean_anomaly))
            + 0.020 * math.sin(rad(2 * mean_anomaly))
            + 282.634
        ) % 360
        right_ascension = deg(math.atan(0.91764 * math.tan(rad(true_longitude)))) % 360
        right_ascension += (true_longitude // 90) * 90 - (right_ascension // 90) * 90
        right_ascension /= 15
        sin_dec = 0.39782 * math.sin(rad(true_longitude))
        cos_dec = math.cos(math.asin(sin_dec))
        cos_hour = (math.cos(rad(cls.ZENITH)) - sin_dec * math.sin(rad(latitude))) / (
            cos_dec * math.cos(rad(latitude))
        )
        if not -1 <= cos_hour <= 1:
            return None  # polar day or night
        hour_angle = (360 - deg(math.acos(cos_hour)) if rising else deg(math.acos(cos_hour))) / 15
        local_mean = hour_angle + right_ascension - 0.06571 * t - 6.622
        return (local_mean - lng_hour) % 24

    @classmethod
    def event(
        cls, day: date, latitude: float, longitude: float, zone: ZoneInfo, rising: bool
    ) -> datetime | None:
        """Local time of sunrise (``rising``) or sunset on ``day``."""
        hours = cls._utc_hours(day, latitude, longitude, rising)
        if hours is None:
            return None
        moment = (datetime.combine(day, time(), tzinfo=timezone.utc) + timedelta(hours=hours)).astimezone(zone)
        # The UTC hour wraps at midnight; keep the event on the requested local day.
        return moment + timedelta(days=(day - moment.date()).days)

    @classmethod
    def times(
        cls, day: date, latitude: float, longitude: float, zone: ZoneInfo
    ) -> dict[str, datetime | None]:
        return {
            "sunrise": cls.event(day, latitude, longitude, zone, rising=True),
            "sunset": cls.event(day, latitude, longitude, zone, rising=False),
        }
