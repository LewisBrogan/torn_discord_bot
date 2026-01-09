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
