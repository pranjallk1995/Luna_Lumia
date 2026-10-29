"""PostgreSQL schema and connection pool for Luna Lumia."""

from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Cursor
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import AppConfig


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lights (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, ip_address INET NOT NULL UNIQUE,
 mac_address TEXT UNIQUE,
 protocol TEXT NOT NULL DEFAULT 'wiz', is_on BOOLEAN NOT NULL DEFAULT FALSE,
 brightness SMALLINT NOT NULL DEFAULT 100 CHECK (brightness BETWEEN 1 AND 100),
 color CHAR(7) NOT NULL DEFAULT '#FFFFFF', reachable BOOLEAN,
 last_seen TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE lights ADD COLUMN IF NOT EXISTS mac_address TEXT;
ALTER TABLE lights ADD COLUMN IF NOT EXISTS background_image_url TEXT;
ALTER TABLE lights ADD COLUMN IF NOT EXISTS color_temp SMALLINT NOT NULL DEFAULT 4000
    CHECK (color_temp BETWEEN 2200 AND 6500);
CREATE UNIQUE INDEX IF NOT EXISTS lights_mac_address_idx
    ON lights (mac_address) WHERE mac_address IS NOT NULL;
CREATE TABLE IF NOT EXISTS room_images (
 room_key TEXT PRIMARY KEY,
 image_url TEXT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO room_images (room_key, image_url) VALUES
 ('bathroom','https://visia-mcp.lunaapps.fyi/api/public/images/bfd38d22-352c-401f-9ee6-9c986ae567ed'),
 ('dining_room','https://visia-mcp.lunaapps.fyi/api/public/images/e8e72094-4572-4501-9545-509d6d81b368'),
 ('entrance','https://visia-mcp.lunaapps.fyi/api/public/images/73e1e826-7679-42c3-bfe0-5425e3931230'),
 ('home_office','https://visia-mcp.lunaapps.fyi/api/public/images/57f8631b-f52a-4e82-af16-b7806bfd967e'),
 ('kitchen','https://visia-mcp.lunaapps.fyi/api/public/images/745604e7-a749-42fc-b546-bb9d64d4582b'),
 ('living_room','https://visia-mcp.lunaapps.fyi/api/public/images/21b475c5-8168-47fe-bd27-dec8b3328d4e'),
 ('balcony','https://visia-mcp.lunaapps.fyi/api/public/images/95fa3e80-2e6c-4f2c-8d19-9ca25d229294'),
 ('bedroom','https://visia-mcp.lunaapps.fyi/api/public/images/2d77a066-d097-4b1b-9682-c9eb41538b26')
ON CONFLICT (room_key) DO NOTHING;
CREATE TABLE IF NOT EXISTS light_groups (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, background_image_url TEXT,
 kind TEXT NOT NULL DEFAULT 'room',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE light_groups ADD COLUMN IF NOT EXISTS background_image_url TEXT;
ALTER TABLE light_groups ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'room';
CREATE TABLE IF NOT EXISTS group_members (
 group_id BIGINT REFERENCES light_groups(id) ON DELETE CASCADE,
 light_id BIGINT REFERENCES lights(id) ON DELETE CASCADE,
 membership_kind TEXT NOT NULL DEFAULT 'room',
 PRIMARY KEY(group_id, light_id)
);
ALTER TABLE group_members
    ADD COLUMN IF NOT EXISTS membership_kind TEXT NOT NULL DEFAULT 'room';
UPDATE group_members gm
SET membership_kind = lg.kind
FROM light_groups lg
WHERE lg.id = gm.group_id AND gm.membership_kind IS DISTINCT FROM lg.kind;
DROP INDEX IF EXISTS group_members_one_room_per_light_idx;
CREATE UNIQUE INDEX IF NOT EXISTS group_members_one_room_per_light_idx
    ON group_members (light_id) WHERE membership_kind = 'room';
CREATE TABLE IF NOT EXISTS scenes (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, color CHAR(7) NOT NULL,
 brightness SMALLINT NOT NULL CHECK (brightness BETWEEN 1 AND 100)
);
CREATE TABLE IF NOT EXISTS schedules (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 target_type TEXT NOT NULL, target_id BIGINT, action TEXT NOT NULL,
 scene_id BIGINT REFERENCES scenes(id) ON DELETE SET NULL, run_time TIME NOT NULL,
 weekdays SMALLINT[] NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE,
 last_run_date DATE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO lights (name, ip_address) VALUES ('Living room light', '192.168.1.8')
ON CONFLICT (ip_address) DO NOTHING;
-- Schedules run at a fixed time, or at sunrise/sunset (plus an offset) for the saved location.
ALTER TABLE schedules ALTER COLUMN run_time DROP NOT NULL;
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS time_mode TEXT NOT NULL DEFAULT 'time'
    CHECK (time_mode IN ('time', 'sunrise', 'sunset'));
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS offset_minutes SMALLINT NOT NULL DEFAULT 0
    CHECK (offset_minutes BETWEEN -180 AND 180);
CREATE TABLE IF NOT EXISTS location (
 id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
 name TEXT NOT NULL,
 latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
 longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS transitions (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
 duration_ms INTEGER NOT NULL CHECK (duration_ms BETWEEN 0 AND 600000),
 curve TEXT NOT NULL DEFAULT 'ease-in-out'
  CHECK (curve IN ('linear', 'ease-in', 'ease-out', 'ease-in-out')),
 is_preset BOOLEAN NOT NULL DEFAULT FALSE
);
-- Schemes are solid (one color or temperature) or a sequence of steps with
-- transitions; built-in presets (is_preset) are installed by app/presets.py.
ALTER TABLE scenes ALTER COLUMN color DROP NOT NULL;
ALTER TABLE scenes ALTER COLUMN brightness DROP NOT NULL;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'solid';
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS color_temp SMALLINT
    CHECK (color_temp BETWEEN 2200 AND 6500);
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS steps JSONB NOT NULL DEFAULT '[]';
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS loops BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS is_preset BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE scenes SET is_preset = TRUE
WHERE NOT is_preset AND (name, color, brightness) IN
 (('Warm evening', '#FFB36B', 55), ('Focus', '#E8F1FF', 100), ('Night light', '#FF6B3D', 12));
-- Weather for a day, as periods (start time + condition) sent by an LLM client.
CREATE TABLE IF NOT EXISTS weather_days (
 day DATE PRIMARY KEY,
 location TEXT, summary TEXT, source TEXT,
 periods JSONB NOT NULL DEFAULT '[]',
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Which scheme plays for each weather condition by day and by night.
CREATE TABLE IF NOT EXISTS weather_schemes (
 condition TEXT NOT NULL,
 daypart TEXT NOT NULL CHECK (daypart IN ('day', 'night')),
 scene_id BIGINT REFERENCES scenes(id) ON DELETE SET NULL,
 PRIMARY KEY (condition, daypart)
);
-- Optional automation that applies the matching scheme as the weather changes.
CREATE TABLE IF NOT EXISTS weather_automation (
 id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
 enabled BOOLEAN NOT NULL DEFAULT FALSE,
 target_type TEXT NOT NULL DEFAULT 'on',
 target_id BIGINT,
 last_applied TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Which scheme plays for each mood of the music Luna Vibia plays.
CREATE TABLE IF NOT EXISTS music_schemes (
 mood TEXT PRIMARY KEY,
 scene_id BIGINT REFERENCES scenes(id) ON DELETE SET NULL
);
-- Optional automation that applies the mood's scheme as Vibia's tracks change.
CREATE TABLE IF NOT EXISTS music_automation (
 id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
 enabled BOOLEAN NOT NULL DEFAULT FALSE,
 target_type TEXT NOT NULL DEFAULT 'on',
 target_id BIGINT,
 last_applied TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Beat pulses on top of the music schemes, timed to Vibia's playback clock.
ALTER TABLE music_automation ADD COLUMN IF NOT EXISTS beats BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE music_automation ADD COLUMN IF NOT EXISTS beat_offset_ms INTEGER NOT NULL DEFAULT 300;
ALTER TABLE music_automation ADD COLUMN IF NOT EXISTS beat_strength REAL NOT NULL DEFAULT 1;
"""


class Database:
    """Own the connection pool; each cursor block runs in one transaction."""

    def __init__(self, url: str) -> None:
        self.pool = ConnectionPool(url, min_size=1, max_size=AppConfig.DB_POOL_MAX_SIZE, open=False)

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    def initialize_schema(self) -> None:
        with self.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)

    @contextmanager
    def cursor(self) -> Iterator[Cursor]:
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                yield cursor
