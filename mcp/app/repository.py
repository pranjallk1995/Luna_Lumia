from datetime import date
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from .database import Database
from .models import GroupCreate, LightCreate, SceneCreate, ScheduleCreate


class LumiaRepository:
    def __init__(self, database: Database): self.database = database
    def ensure_schema(self): self.database.initialize_schema()

    @staticmethod
    def serialize(row):
        if not row: return None
        return {key: (value.isoformat() if hasattr(value, "isoformat") else str(value) if key == "ip_address" else value) for key, value in row.items()}

    def list_lights(self):
        with self.database.cursor() as c:
            c.execute("SELECT * FROM lights ORDER BY LOWER(name), id")
            return [self.serialize(row) for row in c.fetchall()]

    @staticmethod
    def room_key_for_name(name: str) -> str:
        normalized = name.lower()
        matches = (
            (("bath", "washroom"), "bathroom"),
            (("bed",), "bedroom"),
            (("balcony", "terrace", "patio"), "balcony"),
            (("kitchen",), "kitchen"),
            (("dining",), "dining_room"),
            (("office", "study", "desk"), "home_office"),
            (("entrance", "entry", "hall", "foyer"), "entrance"),
            (("living", "lounge",), "living_room"),
        )
        for keywords, room_key in matches:
            if any(keyword in normalized for keyword in keywords):
                return room_key
        return "living_room"

    def lights_with_room_images(self):
        lights = self.list_lights()
        images = {item["room_key"]: item["image_url"] for item in self.list_room_images()}
        fallback = images.get("living_room") or next(iter(images.values()), None)
        for light in lights:
            room_key = self.room_key_for_name(light["name"])
            light["room_key"] = room_key
            light["effective_image_url"] = light.get("background_image_url") or images.get(room_key) or fallback
        return lights

    def light(self, light_id: int):
        with self.database.cursor() as c:
            c.execute("SELECT * FROM lights WHERE id=%s", (light_id,))
            return self.serialize(c.fetchone())

    def add_light(self, entry: LightCreate):
        with self.database.cursor() as c:
            c.execute("INSERT INTO lights(name,ip_address,protocol,mac_address) VALUES(%s,%s,%s,%s) RETURNING *", (entry.name.strip(), entry.ip_address, entry.protocol, entry.mac_address))
            return self.serialize(c.fetchone())

    def store_mac_address(self, light_id: int, mac_address: str):
        with self.database.cursor() as c:
            c.execute("UPDATE lights SET mac_address=%s WHERE id=%s RETURNING *", (mac_address, light_id))
            return self.serialize(c.fetchone())

    def delete_light(self, light_id: int):
        with self.database.cursor() as c:
            c.execute("DELETE FROM lights WHERE id=%s RETURNING id", (light_id,))
            return c.fetchone() is not None

    def rename_light(self, light_id: int, name: str):
        with self.database.cursor() as c:
            c.execute("UPDATE lights SET name=%s WHERE id=%s RETURNING *", (name, light_id))
            return self.serialize(c.fetchone())

    def update_light_image(self, light_id: int, image_url: str | None):
        with self.database.cursor() as c:
            c.execute("UPDATE lights SET background_image_url=%s WHERE id=%s RETURNING *", (image_url, light_id))
            return self.serialize(c.fetchone())

    @staticmethod
    def image_scheme_key(image_url: str | None) -> str | None:
        if not image_url:
            return None
        parsed = urlsplit(image_url)
        path = parsed.path
        marker = "/api/public/images/"
        scheme_path = path.split(marker, 1)[0] + marker if marker in path else path.rsplit("/", 1)[0] + "/"
        return f"{parsed.scheme}://{parsed.netloc}{scheme_path}"

    def assign_inferred_light_image(self, light_id: int, room_name: str | None = None):
        light = self.light(light_id)
        if not light:
            raise ValueError("Light not found")
        images = self.list_room_images()
        if not images:
            raise ValueError("No room images are configured")

        room_source = (room_name or "").strip() or light["name"]
        room_key = self.room_key_for_name(room_source)
        scheme_counts = Counter(
            self.image_scheme_key(image["image_url"]) for image in images
        )
        existing_scheme = self.image_scheme_key(light.get("background_image_url"))
        preferred_scheme = (
            existing_scheme
            if existing_scheme in scheme_counts
            else scheme_counts.most_common(1)[0][0]
        )

        def matching(candidate_room: str, candidate_scheme: str | None = None):
            return next(
                (
                    image
                    for image in images
                    if image["room_key"] == candidate_room
                    and (
                        candidate_scheme is None
                        or self.image_scheme_key(image["image_url"]) == candidate_scheme
                    )
                ),
                None,
            )

        selected = (
            matching(room_key, preferred_scheme)
            or matching("living_room", preferred_scheme)
            or matching(room_key)
            or matching("living_room")
            or images[0]
        )
        assigned = self.update_light_image(light_id, selected["image_url"])
        assigned["inferred_room_key"] = room_key
        assigned["image_scheme"] = self.image_scheme_key(selected["image_url"])
        assigned["effective_image_url"] = selected["image_url"]
        assigned["inference_source"] = "room_name" if room_name and room_name.strip() else "light_name"
        return assigned

    def list_room_images(self):
        with self.database.cursor() as c:
            c.execute("SELECT room_key,image_url,updated_at FROM room_images ORDER BY room_key")
            return [self.serialize(row) for row in c.fetchall()]

    def update_room_image(self, room_key: str, image_url: str):
        with self.database.cursor() as c:
            c.execute("""INSERT INTO room_images(room_key,image_url) VALUES(%s,%s)
                ON CONFLICT(room_key) DO UPDATE SET image_url=EXCLUDED.image_url,updated_at=NOW()
                RETURNING *""", (room_key, image_url))
            return self.serialize(c.fetchone())

    def update_state(self, light_id: int, *, on=None, brightness=None, color=None, reachable=None):
        with self.database.cursor() as c:
            c.execute("""UPDATE lights SET is_on=COALESCE(%s,is_on), brightness=COALESCE(%s,brightness),
                color=COALESCE(%s,color), reachable=COALESCE(%s,reachable), last_seen=CASE WHEN %s THEN NOW() ELSE last_seen END
                WHERE id=%s RETURNING *""", (on, brightness, color, reachable, reachable is True, light_id))
            return self.serialize(c.fetchone())

    def target_lights(self, target_type: str, target_id: int | None):
        with self.database.cursor() as c:
            if target_type == "all": c.execute("SELECT * FROM lights ORDER BY id")
            elif target_type == "light": c.execute("SELECT * FROM lights WHERE id=%s", (target_id,))
            else: c.execute("SELECT l.* FROM lights l JOIN group_members gm ON gm.light_id=l.id WHERE gm.group_id=%s ORDER BY l.id", (target_id,))
            return [self.serialize(row) for row in c.fetchall()]

    def list_groups(self):
        with self.database.cursor() as c:
            c.execute("""SELECT g.*, COALESCE(array_agg(gm.light_id) FILTER (WHERE gm.light_id IS NOT NULL),'{}') light_ids
                FROM light_groups g LEFT JOIN group_members gm ON gm.group_id=g.id GROUP BY g.id ORDER BY g.name""")
            return [self.serialize(row) for row in c.fetchall()]

    def add_group(self, entry: GroupCreate):
        with self.database.cursor() as c:
            c.execute("INSERT INTO light_groups(name) VALUES(%s) RETURNING *", (entry.name.strip(),)); row=c.fetchone()
            for light_id in entry.light_ids: c.execute("INSERT INTO group_members VALUES(%s,%s) ON CONFLICT DO NOTHING", (row["id"], light_id))
            result=self.serialize(row); result["light_ids"]=entry.light_ids; return result

    def delete_group(self, group_id: int):
        with self.database.cursor() as c:
            c.execute("DELETE FROM light_groups WHERE id=%s RETURNING id", (group_id,)); return c.fetchone() is not None

    def list_scenes(self):
        with self.database.cursor() as c: c.execute("SELECT * FROM scenes ORDER BY name"); return [self.serialize(row) for row in c.fetchall()]

    def scene(self, scene_id: int):
        with self.database.cursor() as c: c.execute("SELECT * FROM scenes WHERE id=%s", (scene_id,)); return self.serialize(c.fetchone())

    def add_scene(self, entry: SceneCreate):
        with self.database.cursor() as c: c.execute("INSERT INTO scenes(name,color,brightness) VALUES(%s,%s,%s) RETURNING *", (entry.name.strip(),entry.color.upper(),entry.brightness)); return self.serialize(c.fetchone())

    def delete_scene(self, scene_id: int):
        with self.database.cursor() as c: c.execute("DELETE FROM scenes WHERE id=%s RETURNING id",(scene_id,)); return c.fetchone() is not None

    def list_schedules(self):
        with self.database.cursor() as c: c.execute("SELECT * FROM schedules ORDER BY run_time,name"); return [self.serialize(row) for row in c.fetchall()]

    def add_schedule(self, entry: ScheduleCreate):
        with self.database.cursor() as c:
            c.execute("""INSERT INTO schedules(name,kind,target_type,target_id,action,scene_id,run_time,weekdays,enabled)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", (entry.name.strip(),entry.kind,entry.target_type,entry.target_id,entry.action,entry.scene_id,entry.run_time,entry.weekdays,entry.enabled))
            return self.serialize(c.fetchone())

    def delete_schedule(self, schedule_id: int):
        with self.database.cursor() as c: c.execute("DELETE FROM schedules WHERE id=%s RETURNING id",(schedule_id,)); return c.fetchone() is not None

    def due_schedules(self, today: date, weekday: int, now_time):
        with self.database.cursor() as c:
            c.execute("SELECT * FROM schedules WHERE enabled AND %s=ANY(weekdays) AND run_time<=%s AND last_run_date IS DISTINCT FROM %s",(weekday,now_time,today))
            return [self.serialize(row) for row in c.fetchall()]

    def mark_ran(self, schedule_id: int, day: date):
        with self.database.cursor() as c: c.execute("UPDATE schedules SET last_run_date=%s WHERE id=%s",(day,schedule_id))
