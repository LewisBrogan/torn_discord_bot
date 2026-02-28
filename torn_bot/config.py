import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

TORN_API_BASE = "https://api.torn.com"

DATABASE_PATH = str(DATA_DIR / "torn_keys.db")

OWNER_IDS = {593139411844071437}

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").strip()
ENCRYPTION_KEY_FILE = str(BASE_DIR / "encryption.key")


def _int_env(name: str, default: int) -> int:
    val = os.getenv(name, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


FACTION_LEADERBOARD_CHANNEL_ID = _int_env(
    "FACTION_LEADERBOARD_CHANNEL_ID",
    1459194617139564636,
)

DAILY_LEADERBOARD_HOUR = _int_env("DAILY_LEADERBOARD_HOUR", 23)
DAILY_LEADERBOARD_MINUTE = _int_env("DAILY_LEADERBOARD_MINUTE", 55)

FLIGHT_ALERT_CHANNEL_ID = _int_env("FLIGHT_ALERT_CHANNEL_ID", 1198410711198605534)
FLIGHT_CHECK_INTERVAL_S = _int_env("FLIGHT_CHECK_INTERVAL_S", 60)
FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY", "").strip()
FLIGHT_IDS_FILE = os.getenv(
    "FLIGHT_IDS_FILE",
    str(DATA_DIR / "flight_ids.json"),
).strip()
FLIGHT_MENTION_USER_ID = _int_env("FLIGHT_MENTION_USER_ID", 593139411844071437)
