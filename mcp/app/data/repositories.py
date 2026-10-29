"""PostgreSQL persistence for Luna Lumia, one repository per aggregate."""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg.types.json import Jsonb

from app.data.database import Database
from app.core.models import (
    CollectionKind,
    GroupCreate,
    LightCreate,
    LocationUpdate,
    SceneCreate,
    ScheduleCreate,
    TransitionCreate,
    WeatherAutomationUpdate,
    WeatherReport,
)

Row = dict[str, Any]


class Repository:
    """Shared query helpers that serialize rows into JSON-friendly dicts."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def serialize(row: Row | None) -> Row | None:
        if not row:
            return None
        return {
            key: (
                value.isoformat()
                if hasattr(value, "isoformat")
                else str(value) if key == "ip_address" else value
            )
            for key, value in row.items()
        }

    def fetch_one(self, sql: str, params: tuple = ()) -> Row | None:
        with self.database.cursor() as cursor:
            cursor.execute(sql, params)
            return self.serialize(cursor.fetchone())

    def fetch_all(self, sql: str, params: tuple = ()) -> list[Row]:
        with self.database.cursor() as cursor:
            cursor.execute(sql, params)
            return [self.serialize(row) for row in cursor.fetchall()]

    def affects_row(self, sql: str, params: tuple = ()) -> bool:
        """Run a statement ending in RETURNING and report whether a row matched."""
        with self.database.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone() is not None


class LightRepository(Repository):
    def list(self) -> list[Row]:
        return self.fetch_all("SELECT * FROM lights ORDER BY LOWER(name), id")

    def get(self, light_id: int) -> Row | None:
        return self.fetch_one("SELECT * FROM lights WHERE id=%s", (light_id,))

    def add(self, entry: LightCreate) -> Row | None:
        return self.fetch_one(
            "INSERT INTO lights(name,ip_address,protocol,mac_address) "
            "VALUES(%s,%s,%s,%s) RETURNING *",
            (entry.name, entry.ip_address, entry.protocol, entry.mac_address),
        )

    def delete(self, light_id: int) -> bool:
        return self.affects_row("DELETE FROM lights WHERE id=%s RETURNING id", (light_id,))

    def rename(self, light_id: int, name: str) -> Row | None:
        return self.fetch_one(
            "UPDATE lights SET name=%s WHERE id=%s RETURNING *", (name, light_id)
        )

    def store_mac_address(self, light_id: int, mac_address: str) -> Row | None:
        return self.fetch_one(
            "UPDATE lights SET mac_address=%s WHERE id=%s RETURNING *",
            (mac_address, light_id),
        )

    def relocate(self, new_ips: dict[int, str]) -> None:
        """Move lights to new IPs atomically, even when lights swap addresses.

        Moving lights are first parked on unique placeholder addresses
        (0.0.0.0 + id) so intermediate states never violate the UNIQUE IP rule.
        """
        if not new_ips:
            return
        with self.database.cursor() as cursor:
            for light_id in new_ips:
                cursor.execute(
                    "UPDATE lights SET ip_address='0.0.0.0'::inet + id WHERE id=%s", (light_id,)
                )
            for light_id, ip_address in new_ips.items():
                cursor.execute(
                    "UPDATE lights SET ip_address=%s WHERE id=%s", (ip_address, light_id)
                )

    def update_image(self, light_id: int, image_url: str | None) -> Row | None:
        return self.fetch_one(
            "UPDATE lights SET background_image_url=%s WHERE id=%s RETURNING *",
            (image_url, light_id),
        )

    def update_state(
        self,
        light_id: int,
        *,
        on=None,
        brightness=None,
        color=None,
        color_temp=None,
        reachable=None,
    ) -> Row | None:
        return self.fetch_one(
            """UPDATE lights SET is_on=COALESCE(%s,is_on), brightness=COALESCE(%s,brightness),
            color=COALESCE(%s,color), color_temp=COALESCE(%s,color_temp),
            reachable=COALESCE(%s,reachable),
            last_seen=CASE WHEN %s THEN NOW() ELSE last_seen END
            WHERE id=%s RETURNING *""",
            (on, brightness, color, color_temp, reachable, reachable is True, light_id),
        )

    def targets(self, target_type: str, target_id: int | None) -> list[Row]:
        """Resolve all lights, lights currently on, one light, or a room/group's members."""
        if target_type == "all":
            return self.fetch_all("SELECT * FROM lights ORDER BY id")
        if target_type == "on":
            return self.fetch_all("SELECT * FROM lights WHERE is_on ORDER BY id")
        if target_type == "light":
            return self.fetch_all("SELECT * FROM lights WHERE id=%s", (target_id,))
        return self.fetch_all(
            "SELECT l.* FROM lights l JOIN group_members gm ON gm.light_id=l.id "
            "WHERE gm.group_id=%s ORDER BY l.id",
            (target_id,),
        )


class CollectionRepository(Repository):
    """Rooms (exclusive membership) and groups (overlapping membership)."""

    SELECT = """SELECT g.*,
        COALESCE(array_agg(gm.light_id) FILTER (WHERE gm.light_id IS NOT NULL),'{}') light_ids,
        COALESCE(array_agg(l.name) FILTER (WHERE l.id IS NOT NULL),'{}') light_names,
        COALESCE(array_agg(l.background_image_url) FILTER (WHERE l.background_image_url IS NOT NULL),'{}') light_image_urls
        FROM light_groups g
        LEFT JOIN group_members gm ON gm.group_id=g.id
        LEFT JOIN lights l ON l.id=gm.light_id
        WHERE (%s::text IS NULL OR g.kind=%s) AND (%s::bigint IS NULL OR g.id=%s)
        GROUP BY g.id ORDER BY g.name"""

    def list(self, kind: CollectionKind | None = None) -> list[Row]:
        return self.fetch_all(self.SELECT, (kind, kind, None, None))

    def get(self, collection_id: int, kind: CollectionKind | None = None) -> Row | None:
        return self.fetch_one(self.SELECT, (kind, kind, collection_id, collection_id))

    def room_conflicts(self, light_ids: list[int]) -> list[Row]:
        """Return lights among ``light_ids`` that already belong to a room."""
        return self.fetch_all(
            """SELECT l.name light_name,g.name room_name
            FROM group_members gm
            JOIN lights l ON l.id=gm.light_id
            JOIN light_groups g ON g.id=gm.group_id
            WHERE gm.membership_kind='room' AND gm.light_id=ANY(%s)
            ORDER BY l.name""",
            (light_ids,),
        )

    def add(self, entry: GroupCreate, kind: CollectionKind) -> int:
        with self.database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO light_groups(name,kind) VALUES(%s,%s) RETURNING id",
                (entry.name, kind),
            )
            collection_id = cursor.fetchone()["id"]
            self._insert_members(cursor, collection_id, entry.light_ids, kind)
        return collection_id

    def add_members(
        self, collection_id: int, light_ids: list[int], kind: CollectionKind
    ) -> None:
        with self.database.cursor() as cursor:
            self._insert_members(cursor, collection_id, light_ids, kind)

    @staticmethod
    def _insert_members(cursor, collection_id: int, light_ids: list[int], kind: str) -> None:
        for light_id in light_ids:
            cursor.execute(
                "INSERT INTO group_members(group_id,light_id,membership_kind) "
                "VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (collection_id, light_id, kind),
            )

    def remove_member(self, collection_id: int, light_id: int) -> bool:
        return self.affects_row(
            "DELETE FROM group_members WHERE group_id=%s AND light_id=%s RETURNING light_id",
            (collection_id, light_id),
        )

    def rename(self, collection_id: int, name: str) -> bool:
        return self.affects_row(
            "UPDATE light_groups SET name=%s WHERE id=%s RETURNING id",
            (name, collection_id),
        )

    def update_image(self, collection_id: int, image_url: str | None) -> Row | None:
        return self.fetch_one(
            "UPDATE light_groups SET background_image_url=%s WHERE id=%s RETURNING *",
            (image_url, collection_id),
        )

    def delete(self, collection_id: int, kind: CollectionKind | None = None) -> bool:
        return self.affects_row(
            "DELETE FROM light_groups WHERE id=%s AND (%s::text IS NULL OR kind=%s) RETURNING id",
            (collection_id, kind, kind),
        )


class RoomImageRepository(Repository):
    def list(self) -> list[Row]:
        return self.fetch_all(
            "SELECT room_key,image_url,updated_at FROM room_images ORDER BY room_key"
        )

    def upsert(self, room_key: str, image_url: str) -> Row | None:
        return self.fetch_one(
            """INSERT INTO room_images(room_key,image_url) VALUES(%s,%s)
            ON CONFLICT(room_key) DO UPDATE SET image_url=EXCLUDED.image_url,updated_at=NOW()
            RETURNING *""",
            (room_key, image_url),
        )


class SceneRepository(Repository):
    """Solid and sequence schemes; built-in presets are refreshed, never deleted."""

    COLUMNS = "name,kind,color,color_temp,brightness,steps,loops,is_preset"

    @staticmethod
    def values(entry: SceneCreate, is_preset: bool) -> tuple:
        steps = [step.model_dump() for step in entry.steps]
        return (
            entry.name, entry.kind, entry.color, entry.color_temp, entry.brightness,
            Jsonb(steps), entry.loops, is_preset,
        )

    def list(self) -> list[Row]:
        return self.fetch_all("SELECT * FROM scenes ORDER BY is_preset DESC, kind, name")

    def get(self, scene_id: int) -> Row | None:
        return self.fetch_one("SELECT * FROM scenes WHERE id=%s", (scene_id,))

    def add(self, entry: SceneCreate) -> Row | None:
        return self.fetch_one(
            f"INSERT INTO scenes({self.COLUMNS}) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            self.values(entry, False),
        )

    def upsert_preset(self, entry: SceneCreate) -> None:
        """Install or refresh a built-in scheme; a user scheme with that name is kept."""
        with self.database.cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO scenes({self.COLUMNS}) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (name) DO UPDATE SET kind=EXCLUDED.kind, color=EXCLUDED.color,
                    color_temp=EXCLUDED.color_temp, brightness=EXCLUDED.brightness,
                    steps=EXCLUDED.steps, loops=EXCLUDED.loops
                WHERE scenes.is_preset""",
                self.values(entry, True),
            )

    def update(self, scene_id: int, entry: SceneCreate) -> Row | None:
        """Replace a user scheme; built-in presets are never changed."""
        return self.fetch_one(
            """UPDATE scenes SET name=%s, kind=%s, color=%s, color_temp=%s, brightness=%s,
                steps=%s, loops=%s
            WHERE id=%s AND NOT is_preset RETURNING *""",
            (*self.values(entry, False)[:-1], scene_id),
        )

    def delete(self, scene_id: int) -> bool:
        return self.affects_row(
            "DELETE FROM scenes WHERE id=%s AND NOT is_preset RETURNING id", (scene_id,)
        )


class TransitionRepository(Repository):
    """Reusable fades between scheme steps."""

    def list(self) -> list[Row]:
        return self.fetch_all("SELECT * FROM transitions ORDER BY duration_ms, name")

    def add(self, entry: TransitionCreate) -> Row | None:
        return self.fetch_one(
            "INSERT INTO transitions(name,duration_ms,curve) VALUES(%s,%s,%s) RETURNING *",
            (entry.name.strip(), entry.duration_ms, entry.curve),
        )

    def upsert_preset(self, entry: TransitionCreate) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO transitions(name,duration_ms,curve,is_preset) VALUES(%s,%s,%s,TRUE)
                ON CONFLICT (name) DO UPDATE SET duration_ms=EXCLUDED.duration_ms,
                    curve=EXCLUDED.curve
                WHERE transitions.is_preset""",
                (entry.name, entry.duration_ms, entry.curve),
            )

    def update(self, transition_id: int, entry: TransitionCreate) -> Row | None:
        """Replace a user transition; built-in presets are never changed."""
        return self.fetch_one(
            "UPDATE transitions SET name=%s, duration_ms=%s, curve=%s "
            "WHERE id=%s AND NOT is_preset RETURNING *",
            (entry.name.strip(), entry.duration_ms, entry.curve, transition_id),
        )

    def delete(self, transition_id: int) -> bool:
        return self.affects_row(
            "DELETE FROM transitions WHERE id=%s AND NOT is_preset RETURNING id", (transition_id,)
        )


class LocationRepository(Repository):
    """The single saved location used for sunrise/sunset schedules."""

    def get(self) -> Row | None:
        return self.fetch_one("SELECT name, latitude, longitude, updated_at FROM location WHERE id=1")

    def save(self, entry: LocationUpdate) -> Row | None:
        return self.fetch_one(
            """INSERT INTO location(id,name,latitude,longitude) VALUES(1,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, latitude=EXCLUDED.latitude,
                longitude=EXCLUDED.longitude, updated_at=NOW()
            RETURNING name, latitude, longitude, updated_at""",
            (entry.name, entry.latitude, entry.longitude),
        )


class ScheduleRepository(Repository):
    def list(self) -> list[Row]:
        return self.fetch_all("SELECT * FROM schedules ORDER BY name")

    def add(self, entry: ScheduleCreate, last_run_date: date | None = None) -> Row | None:
        return self.fetch_one(
            """INSERT INTO schedules(name,kind,target_type,target_id,action,scene_id,time_mode,
                run_time,offset_minutes,weekdays,enabled,last_run_date)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (
                entry.name.strip(), entry.kind, entry.target_type, entry.target_id,
                entry.action, entry.scene_id, entry.time_mode, entry.run_time,
                entry.offset_minutes, entry.weekdays, entry.enabled, last_run_date,
            ),
        )

    def get(self, schedule_id: int) -> Row | None:
        return self.fetch_one("SELECT * FROM schedules WHERE id=%s", (schedule_id,))

    def update(self, schedule_id: int, entry: ScheduleCreate, last_run_date: date | None = None) -> Row | None:
        return self.fetch_one(
            """UPDATE schedules SET name=%s, kind=%s, target_type=%s, target_id=%s, action=%s,
                scene_id=%s, time_mode=%s, run_time=%s, offset_minutes=%s, weekdays=%s, enabled=%s,
                last_run_date=%s
            WHERE id=%s RETURNING *""",
            (
                entry.name.strip(), entry.kind, entry.target_type, entry.target_id,
                entry.action, entry.scene_id, entry.time_mode, entry.run_time,
                entry.offset_minutes, entry.weekdays, entry.enabled, last_run_date, schedule_id,
            ),
        )

    def delete(self, schedule_id: int) -> bool:
        return self.affects_row(
            "DELETE FROM schedules WHERE id=%s RETURNING id", (schedule_id,)
        )

    def pending(self, today: date, weekday: int) -> list[Row]:
        """Enabled schedules for this weekday that have not run today (due time checked by the service)."""
        return self.fetch_all(
            "SELECT * FROM schedules WHERE enabled AND %s=ANY(weekdays) "
            "AND last_run_date IS DISTINCT FROM %s",
            (weekday, today),
        )

    def mark_ran(self, schedule_id: int, day: date) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                "UPDATE schedules SET last_run_date=%s WHERE id=%s", (day, schedule_id)
            )


class WeatherRepository(Repository):
    """One weather report per day."""

    def get(self, day: date) -> Row | None:
        return self.fetch_one("SELECT * FROM weather_days WHERE day=%s", (day,))

    def save(self, report: WeatherReport) -> Row | None:
        periods = [period.model_dump(mode="json") for period in report.periods]
        return self.fetch_one(
            """INSERT INTO weather_days(day,location,summary,source,periods) VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT (day) DO UPDATE SET location=EXCLUDED.location, summary=EXCLUDED.summary,
                source=EXCLUDED.source, periods=EXCLUDED.periods, updated_at=NOW()
            RETURNING *""",
            (report.day, report.location, report.summary, report.source, Jsonb(periods)),
        )

    def delete(self, day: date) -> bool:
        return self.affects_row("DELETE FROM weather_days WHERE day=%s RETURNING day", (day,))


class WeatherSchemeRepository(Repository):
    """The scheme chosen for each (weather condition, day or night) slot."""

    def list(self) -> list[Row]:
        return self.fetch_all(
            """SELECT ws.condition, ws.daypart, ws.scene_id, s.name scheme_name,
                s.kind scheme_kind, s.is_preset scheme_is_preset
            FROM weather_schemes ws LEFT JOIN scenes s ON s.id=ws.scene_id
            ORDER BY ws.condition, ws.daypart"""
        )

    def set(self, condition: str, daypart: str, scene_id: int | None) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO weather_schemes(condition,daypart,scene_id) VALUES(%s,%s,%s)
                ON CONFLICT (condition,daypart) DO UPDATE SET scene_id=EXCLUDED.scene_id""",
                (condition, daypart, scene_id),
            )

    def seed(self, condition: str, daypart: str, scene_id: int) -> None:
        """Point an empty slot (new, or whose scheme was deleted) at its built-in scheme."""
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO weather_schemes(condition,daypart,scene_id) VALUES(%s,%s,%s)
                ON CONFLICT (condition,daypart) DO UPDATE SET scene_id=EXCLUDED.scene_id
                WHERE weather_schemes.scene_id IS NULL""",
                (condition, daypart, scene_id),
            )


class WeatherAutomationRepository(Repository):
    """The single weather-automation setting."""

    TABLE = "weather_automation"
    DEFAULT: Row = {"enabled": False, "target_type": "on", "target_id": None, "last_applied": None}

    def get(self) -> Row:
        row = self.fetch_one(
            f"SELECT enabled,target_type,target_id,last_applied,updated_at FROM {self.TABLE} WHERE id=1"
        )
        return row or dict(self.DEFAULT)

    def save(self, entry: WeatherAutomationUpdate) -> Row | None:
        """Store the setting; clearing last_applied makes it apply on the next tick."""
        return self.fetch_one(
            f"""INSERT INTO {self.TABLE}(id,enabled,target_type,target_id,last_applied)
            VALUES(1,%s,%s,%s,NULL)
            ON CONFLICT (id) DO UPDATE SET enabled=EXCLUDED.enabled, target_type=EXCLUDED.target_type,
                target_id=EXCLUDED.target_id, last_applied=NULL, updated_at=NOW()
            RETURNING enabled,target_type,target_id,last_applied,updated_at""",
            (entry.enabled, entry.target_type, entry.target_id),
        )

    def mark_applied(self, key: str | None) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(f"UPDATE {self.TABLE} SET last_applied=%s WHERE id=1", (key,))


class MusicAutomationRepository(WeatherAutomationRepository):
    """The single music-automation setting."""

    TABLE = "music_automation"


class MusicSchemeRepository(Repository):
    """The scheme chosen for each music mood."""

    def list(self) -> list[Row]:
        return self.fetch_all(
            """SELECT ms.mood, ms.scene_id, s.name scheme_name, s.kind scheme_kind
            FROM music_schemes ms LEFT JOIN scenes s ON s.id=ms.scene_id ORDER BY ms.mood"""
        )

    def set(self, mood: str, scene_id: int | None) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO music_schemes(mood,scene_id) VALUES(%s,%s)
                ON CONFLICT (mood) DO UPDATE SET scene_id=EXCLUDED.scene_id""",
                (mood, scene_id),
            )

    def seed(self, mood: str, scene_id: int) -> None:
        """Point an empty mood (new, or whose scheme was deleted) at its built-in scheme."""
        with self.database.cursor() as cursor:
            cursor.execute(
                """INSERT INTO music_schemes(mood,scene_id) VALUES(%s,%s)
                ON CONFLICT (mood) DO UPDATE SET scene_id=EXCLUDED.scene_id
                WHERE music_schemes.scene_id IS NULL""",
                (mood, scene_id),
            )
