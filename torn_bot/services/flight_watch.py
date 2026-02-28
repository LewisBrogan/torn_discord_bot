import asyncio
import json
import time
from datetime import datetime
import discord

from torn_bot.api.torn_v2 import fetch_torn_v2, TornAPIError
from torn_bot.config import (
    FLIGHT_ALERT_CHANNEL_ID,
    FLIGHT_CHECK_INTERVAL_S,
    FLIGHT_API_KEY,
    FLIGHT_IDS_FILE,
    FLIGHT_MENTION_USER_ID,
)
from torn_bot.storage import KeyStorage


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[flight {ts}] {msg}")

_LAST_STATE: dict[int, tuple[str | None, str | None]] = {}
_LAST_IDS_ERROR: str | None = None


async def _get_channel(client: discord.Client) -> discord.abc.Messageable | None:
    if not FLIGHT_ALERT_CHANNEL_ID:
        return None
    channel = client.get_channel(FLIGHT_ALERT_CHANNEL_ID)
    if channel is not None:
        return channel
    try:
        return await client.fetch_channel(FLIGHT_ALERT_CHANNEL_ID)
    except Exception:
        return None


def _extract_profile(data: dict) -> dict:
    if isinstance(data, dict) and "profile" in data:
        return data.get("profile") or {}
    return data if isinstance(data, dict) else {}


def _returning_to_torn(desc: str | None) -> bool:
    if not desc:
        return False
    d = desc.lower()
    return "torn" in d and ("return" in d or "to torn" in d)


def _log_ids_error(msg: str) -> None:
    global _LAST_IDS_ERROR
    if msg != _LAST_IDS_ERROR:
        _log(msg)
        _LAST_IDS_ERROR = msg


def _load_flight_ids() -> list[int]:
    global _LAST_IDS_ERROR
    if not FLIGHT_IDS_FILE:
        _log_ids_error("flight watch skipped: FLIGHT_IDS_FILE not set")
        return []

    try:
        with open(FLIGHT_IDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        _log_ids_error(f"flight watch skipped: ids file not found {FLIGHT_IDS_FILE}")
        return []
    except Exception as e:
        _log_ids_error(f"flight watch skipped: invalid ids file {FLIGHT_IDS_FILE}: {e}")
        return []

    raw = data.get("ids") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        _log_ids_error("flight watch skipped: ids file must be a JSON array")
        return []

    ids: list[int] = []
    seen: set[int] = set()
    for item in raw:
        if isinstance(item, str):
            parts = [p.strip() for p in item.split(",")] if "," in item else [item.strip()]
            for part in parts:
                if not part:
                    continue
                try:
                    tid = int(part)
                except ValueError:
                    continue
                if tid not in seen:
                    seen.add(tid)
                    ids.append(tid)
        else:
            try:
                tid = int(item)
            except (TypeError, ValueError):
                continue
            if tid not in seen:
                seen.add(tid)
                ids.append(tid)

    _LAST_IDS_ERROR = None
    return ids


async def flight_watch_once(client: discord.Client, storage: KeyStorage) -> None:
    api_key = FLIGHT_API_KEY or storage.get_global_key("flight")
    if not api_key:
        _log("flight watch skipped: no FLIGHT_API_KEY set")
        return

    ids = _load_flight_ids()
    if not ids:
        return

    channel = await _get_channel(client)
    if channel is None:
        _log(f"flight watch skipped: channel {FLIGHT_ALERT_CHANNEL_ID} not accessible")
        return

    current_ids = set(ids)
    for tid in list(_LAST_STATE.keys()):
        if tid not in current_ids:
            _LAST_STATE.pop(tid, None)

    traveling_lines: list[str] = []

    for torn_id in ids:
        last_state, last_description = _LAST_STATE.get(torn_id, (None, None))
        try:
            data = await fetch_torn_v2(f"/user/{torn_id}/basic", api_key=api_key)
        except TornAPIError as e:
            _log(f"flight watch error {torn_id}: {e.message}")
            continue
        except Exception as e:
            _log(f"flight watch error {torn_id}: {e}")
            continue

        profile = _extract_profile(data)
        name = profile.get("name") or str(torn_id)
        status = profile.get("status") or {}
        state = status.get("state") or ""
        description = status.get("description") or status.get("details") or ""

        is_traveling = state == "Traveling"
        if is_traveling:
            desc = description or "Traveling"
            traveling_lines.append(f"{name}[{torn_id}] - {desc}")
        msg = None

        profile_url = f"https://www.torn.com/profiles.php?XID={torn_id}"
        name_link = f"[{name} [{torn_id}]]({profile_url})"

        mention = f"<@{FLIGHT_MENTION_USER_ID}> " if FLIGHT_MENTION_USER_ID else ""

        if (not is_traveling) and last_state == "Traveling":
            if _returning_to_torn(last_description):
                msg = f"{mention}**{name_link}** has landed."

        if msg:
            try:
                await channel.send(msg)
            except Exception as e:
                _log(f"flight watch notify failed {torn_id}: {e}")

        _LAST_STATE[torn_id] = (state or None, description or None)

    if traveling_lines:
        _log(f"{', '.join(traveling_lines)} is flying")
    else:
        _log("no one flying")


async def run_flight_watch_loop(client: discord.Client, storage: KeyStorage) -> None:
    await client.wait_until_ready()
    interval = max(10, FLIGHT_CHECK_INTERVAL_S)
    while not client.is_closed():
        start = time.monotonic()
        try:
            await flight_watch_once(client, storage)
        except Exception as e:
            _log(f"flight watch loop error: {e}")
        elapsed = time.monotonic() - start
        sleep_s = max(1.0, interval - elapsed)
        await asyncio.sleep(sleep_s)
