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

CREATE TABLE IF NOT EXISTS faction_attacks_seen (
  attack_id INTEGER PRIMARY KEY,
  attacker_id INTEGER NOT NULL,
  started INTEGER NOT NULL,
  ended INTEGER,
  result TEXT,
  respect_gain REAL,
  respect_loss REAL,
  attacker_name TEXT,
  defender_id INTEGER,
  defender_name TEXT,
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS faction_leaderboard_totals (
  attacker_id INTEGER PRIMARY KEY,
  attacks INTEGER NOT NULL DEFAULT 0,
  mugs INTEGER NOT NULL DEFAULT 0,
  hosp INTEGER NOT NULL DEFAULT 0,
  respect_gain REAL NOT NULL DEFAULT 0,
  respect_loss REAL NOT NULL DEFAULT 0,
  mugged REAL NOT NULL DEFAULT 0,
  best_mug REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS faction_leaderboard_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    existing_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(faction_attacks_seen)")
    }
    missing = [
        ("ended", "INTEGER"),
        ("result", "TEXT"),
        ("respect_gain", "REAL"),
        ("respect_loss", "REAL"),
        ("attacker_name", "TEXT"),
        ("defender_id", "INTEGER"),
        ("defender_name", "TEXT"),
        ("raw_json", "TEXT"),
    ]
    for col, col_type in missing:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE faction_attacks_seen ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.close()
