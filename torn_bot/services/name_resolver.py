from __future__ import annotations

import asyncio
import time
from typing import Dict, Set, Optional

from torn_bot.api.torn_v2 import get_session

TORN_V1_BASE = "https://api.torn.com"

_USER_NAME_CACHE: Dict[int, tuple[str, float]] = {}
_USER_TTL_SECONDS = 6 * 60 * 60
_FACTION_MEMBER_CACHE: Dict[int, str] = {}
_FACTION_MEMBER_EXPIRES_AT: float = 0.0
_FACTION_MEMBER_TTL_SECONDS = 10 * 60


def _user_cache_get(torn_id: int) -> Optional[str]:
    item = _USER_NAME_CACHE.get(torn_id)
    if not item:
        return None
    name, expires_at = item
    if time.time() >= expires_at:
        _USER_NAME_CACHE.pop(torn_id, None)
        return None
    return name


def _user_cache_set(torn_id: int, name: str) -> None:
    _USER_NAME_CACHE[torn_id] = (name, time.time() + _USER_TTL_SECONDS)


async def _fetch_user_basic_name_v1(api_key: str, torn_id: int) -> Optional[str]:
    """
    v1: /user/{id}?selections=basic

    """
    session = await get_session()
    url = f"{TORN_V1_BASE}/user/{torn_id}"
    params = {"selections": "basic", "key": api_key}

    async with session.get(url, params=params) as resp:
        data = await resp.json()

    if isinstance(data, dict) and "error" in data:
        return None

    name = (data.get("name") or "").strip()
    return name if name else None


async def _refresh_faction_members(api_key: str) -> None:
    """
    v1: /faction/?selections=basic,members a map of member_id -> member_name

    """
    global _FACTION_MEMBER_CACHE, _FACTION_MEMBER_EXPIRES_AT

    session = await get_session()
    url = f"{TORN_V1_BASE}/faction/"
    params = {"selections": "basic,members", "key": api_key}

    async with session.get(url, params=params) as resp:
        data = await resp.json()

    if isinstance(data, dict) and "error" in data:
        _FACTION_MEMBER_CACHE = {}
        _FACTION_MEMBER_EXPIRES_AT = time.time() + 60
        return

    members = data.get("members") or {}
    m: Dict[int, str] = {}

    if isinstance(members, dict):
        for k, v in members.items():
            try:
                tid = int(k)
            except Exception:
                continue
            if not isinstance(v, dict):
                continue
            name = (v.get("name") or "").strip()
            if tid and name:
                m[tid] = name

    _FACTION_MEMBER_CACHE = m
    _FACTION_MEMBER_EXPIRES_AT = time.time() + _FACTION_MEMBER_TTL_SECONDS


async def _get_faction_member_map(api_key: str) -> Dict[int, str]:
    global _FACTION_MEMBER_EXPIRES_AT
    if time.time() >= _FACTION_MEMBER_EXPIRES_AT:
        await _refresh_faction_members(api_key)
    return _FACTION_MEMBER_CACHE


async def resolve_names(api_key: str, ids: Set[int], *, concurrency: int = 10) -> Dict[int, str]:
    """
      1) faction members map (single API)
      2) user name cache
      3) id user basic lookup)
    """
    resolved: Dict[int, str] = {}

    faction_map = await _get_faction_member_map(api_key)
    for tid in ids:
        if tid in faction_map:
            resolved[tid] = faction_map[tid]

    to_fetch: list[int] = []
    for tid in ids:
        if tid <= 0 or tid in resolved:
            continue
        cached = _user_cache_get(tid)
        if cached:
            resolved[tid] = cached
        else:
            to_fetch.append(tid)

    if not to_fetch:
        return resolved

    sem = asyncio.Semaphore(max(1, concurrency))

    async def worker(tid: int) -> None:
        async with sem:
            name = await _fetch_user_basic_name_v1(api_key, tid)
            if name:
                _user_cache_set(tid, name)
                resolved[tid] = name

    await asyncio.gather(*(worker(t) for t in to_fetch))
    return resolved
