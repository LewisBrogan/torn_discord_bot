from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Any

try:
    from zoneinfo import ZoneInfo
    LONDON = ZoneInfo("Europe/London")
except Exception:
    LONDON = timezone.utc

from torn_bot.api.torn_v2 import fetch_torn_v2


def london_day_start_utc_ts() -> int:
    now_lon = datetime.now(tz=LONDON)
    start_lon = now_lon.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_lon.astimezone(timezone.utc)
    return int(start_utc.timestamp())


def fmt_time_london(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(LONDON)
    return dt.strftime("%H:%M:%S")


def result_tag(result: str) -> str:
    r = (result or "").lower()
    if "hospital" in r:
        return "HOSP"
    if "mug" in r:
        return "MUG"
    if "assist" in r:
        return "ASST"
    if "lost" in r:
        return "LOST"
    return "ATK"


async def fetch_faction_attacks_since(
    api_key: str,
    *,
    since_utc: int,
    page_limit: int = 10,
    per_page: int = 100,
) -> List[Dict[str, Any]]:
    all_attacks: List[Dict[str, Any]] = []
    to_param = None

    for _ in range(page_limit):
        params = {"limit": per_page, "sort": "DESC"}
        if to_param is not None:
            params["to"] = to_param

        data = await fetch_torn_v2("/faction/attacksfull", api_key=api_key, params=params)
        attacks = data.get("attacks") or []

        if not attacks:
            break

        for a in attacks:
            started = int(a.get("started", 0) or 0)
            if started >= since_utc:
                all_attacks.append(a)

        oldest_started = int(attacks[-1].get("started", 0) or 0)
        if oldest_started < since_utc:
            break

        to_param = int(attacks[-1].get("ended", 0) or 0)

    return all_attacks


async def fetch_today_faction_attacks(
    api_key: str,
    *,
    page_limit: int = 8,
    per_page: int = 100,
) -> List[Dict[str, Any]]:
    since = london_day_start_utc_ts()
    return await fetch_faction_attacks_since(api_key, since_utc=since, page_limit=page_limit, per_page=per_page)
