"""PostgreSQL persistence for Luna Lumia, one repository per aggregate."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from .database import Database
from .models import CollectionKind, GroupCreate, LightCreate, SceneCreate, ScheduleCreate

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

    def update_image(self, light_id: int, image_url: str | None) -> Row | None:
        return self.fetch_one(
            "UPDATE lights SET background_image_url=%s WHERE id=%s RETURNING *",
            (image_url, light_id),
        )

    def update_state(
        self, light_id: int, *, on=None, brightness=None, color=None, reachable=None
    ) -> Row | None:
        return self.fetch_one(
            """UPDATE lights SET is_on=COALESCE(%s,is_on), brightness=COALESCE(%s,brightness),
            color=COALESCE(%s,color), reachable=COALESCE(%s,reachable),
            last_seen=CASE WHEN %s THEN NOW() ELSE last_seen END
            WHERE id=%s RETURNING *""",
            (on, brightness, color, reachable, reachable is True, light_id),
        )

    def targets(self, target_type: str, target_id: int | None) -> list[Row]:
        """Resolve all lights, one light, or a room/group's member lights."""
        if target_type == "all":
            return self.fetch_all("SELECT * FROM lights ORDER BY id")
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
    def list(self) -> list[Row]:
        return self.fetch_all("SELECT * FROM scenes ORDER BY name")

    def get(self, scene_id: int) -> Row | None:
        return self.fetch_one("SELECT * FROM scenes WHERE id=%s", (scene_id,))

    def add(self, entry: SceneCreate) -> Row | None:
        return self.fetch_one(
            "INSERT INTO scenes(name,color,brightness) VALUES(%s,%s,%s) RETURNING *",
            (entry.name.strip(), entry.color.upper(), entry.brightness),
        )

    def delete(self, scene_id: int) -> bool:
        return self.affects_row("DELETE FROM scenes WHERE id=%s RETURNING id", (scene_id,))


class ScheduleRepository(Repository):
    def list(self) -> list[Row]:
        return self.fetch_all("SELECT * FROM schedules ORDER BY run_time,name")

    def add(self, entry: ScheduleCreate) -> Row | None:
        return self.fetch_one(
            """INSERT INTO schedules(name,kind,target_type,target_id,action,scene_id,run_time,weekdays,enabled)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (
                entry.name.strip(), entry.kind, entry.target_type, entry.target_id,
                entry.action, entry.scene_id, entry.run_time, entry.weekdays, entry.enabled,
            ),
        )

    def delete(self, schedule_id: int) -> bool:
        return self.affects_row(
            "DELETE FROM schedules WHERE id=%s RETURNING id", (schedule_id,)
        )

    def due(self, today: date, weekday: int, now_time: time) -> list[Row]:
        return self.fetch_all(
            "SELECT * FROM schedules WHERE enabled AND %s=ANY(weekdays) "
            "AND run_time<=%s AND last_run_date IS DISTINCT FROM %s",
            (weekday, now_time, today),
        )

    def mark_ran(self, schedule_id: int, day: date) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                "UPDATE schedules SET last_run_date=%s WHERE id=%s", (day, schedule_id)
            )
