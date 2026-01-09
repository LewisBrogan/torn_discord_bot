import os
import sqlite3
from typing import Optional, List
from cryptography.fernet import Fernet

from torn_bot.config import ENCRYPTION_KEY, ENCRYPTION_KEY_FILE
from torn_bot.db import init_db, get_conn


class KeyStorage:
    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)
        init_db()

    def _get_or_create_encryption_key(self) -> bytes:
        if ENCRYPTION_KEY:
            return ENCRYPTION_KEY.encode()

        if os.path.exists(ENCRYPTION_KEY_FILE):
            with open(ENCRYPTION_KEY_FILE, "rb") as f:
                return f.read()

        new_key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, "wb") as f:
            f.write(new_key)
        print(f"[storage] Generated new encryption key saved to {ENCRYPTION_KEY_FILE}")
        return new_key

    def store_key(self, discord_id: int, api_key: str) -> None:
        encrypted = self.cipher.encrypt(api_key.encode()).decode()
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO api_keys (discord_id, encrypted_key) VALUES (?, ?)",
            (discord_id, encrypted),
        )
        conn.commit()
        conn.close()

    def get_key(self, discord_id: int) -> Optional[str]:
        conn = get_conn()
        cur = conn.execute("SELECT encrypted_key FROM api_keys WHERE discord_id = ?", (discord_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return self.cipher.decrypt(row[0].encode()).decode()

    def delete_key(self, discord_id: int) -> bool:
        conn = get_conn()
        cur = conn.execute("DELETE FROM api_keys WHERE discord_id = ?", (discord_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def add_target(self, discord_id: int, torn_id: int) -> bool:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO targets (discord_id, torn_id) VALUES (?, ?)",
                (discord_id, torn_id),
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def remove_target(self, discord_id: int, torn_id: int) -> bool:
        conn = get_conn()
        cur = conn.execute(
            "DELETE FROM targets WHERE discord_id = ? AND torn_id = ?",
            (discord_id, torn_id),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_targets(self, discord_id: int) -> List[int]:
        conn = get_conn()
        cur = conn.execute("SELECT torn_id FROM targets WHERE discord_id = ?", (discord_id,))
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows

    def clear_targets(self, discord_id: int) -> int:
        conn = get_conn()
        cur = conn.execute("DELETE FROM targets WHERE discord_id = ?", (discord_id,))
        count = cur.rowcount
        conn.commit()
        conn.close()
        return count
    def store_global_key(self, name: str, api_key: str) -> None:
        encrypted = self.cipher.encrypt(api_key.encode()).decode()
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO global_keys (name, encrypted_key) VALUES (?, ?)",
            (name, encrypted),
        )
        conn.commit()
        conn.close()

    def get_global_key(self, name: str) -> Optional[str]:
        conn = get_conn()
        cur = conn.execute(
            "SELECT encrypted_key FROM global_keys WHERE name = ?",
            (name,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return self.cipher.decrypt(row[0].encode()).decode()

    def delete_global_key(self, name: str) -> bool:
        conn = get_conn()
        cur = conn.execute("DELETE FROM global_keys WHERE name = ?", (name,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted