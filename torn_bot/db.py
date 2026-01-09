import sqlite3
from torn_bot.config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
  discord_id INTEGER PRIMARY KEY,
  encrypted_key TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS targets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_id INTEGER NOT NULL,
  torn_id INTEGER NOT NULL,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(discord_id, torn_id)
);

CREATE TABLE IF NOT EXISTS global_keys (
  name TEXT PRIMARY KEY,
  encrypted_key TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
