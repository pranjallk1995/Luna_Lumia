import os
from contextlib import contextmanager
from dataclasses import dataclass

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


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
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE light_groups ADD COLUMN IF NOT EXISTS background_image_url TEXT;
CREATE TABLE IF NOT EXISTS group_members (
 group_id BIGINT REFERENCES light_groups(id) ON DELETE CASCADE,
 light_id BIGINT REFERENCES lights(id) ON DELETE CASCADE,
 PRIMARY KEY(group_id, light_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS group_members_one_room_per_light_idx
    ON group_members (light_id);
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
INSERT INTO scenes (name, color, brightness) VALUES
 ('Warm evening', '#FFB36B', 55), ('Focus', '#E8F1FF', 100), ('Night light', '#FF6B3D', 12)
ON CONFLICT (name) DO NOTHING;
"""


@dataclass
class Database:
    url: str

    def __post_init__(self):
        self.pool = ConnectionPool(self.url, min_size=1, max_size=8, open=False)

    @classmethod
    def from_env(cls):
        return cls(os.environ["DATABASE_URL"])

    def open(self): self.pool.open(wait=True)
    def close(self): self.pool.close()
    def initialize_schema(self):
        with self.cursor() as cursor: cursor.execute(SCHEMA_SQL)

    @contextmanager
    def cursor(self):
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                yield cursor
