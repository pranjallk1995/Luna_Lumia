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
CREATE UNIQUE INDEX IF NOT EXISTS lights_mac_address_idx
    ON lights (mac_address) WHERE mac_address IS NOT NULL;
CREATE TABLE IF NOT EXISTS light_groups (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS group_members (
 group_id BIGINT REFERENCES light_groups(id) ON DELETE CASCADE,
 light_id BIGINT REFERENCES lights(id) ON DELETE CASCADE,
 PRIMARY KEY(group_id, light_id)
);
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
