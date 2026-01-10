from __future__ import annotations
from typing import Optional, Dict, Any
import aiohttp
from torn_bot.config import TORN_API_BASE


class TornAPIError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Torn API Error {code}: {message}")


_HTTP_SESSION: aiohttp.ClientSession | None = None


async def get_session() -> aiohttp.ClientSession:
    global _HTTP_SESSION
    if _HTTP_SESSION is None or _HTTP_SESSION.closed:
        _HTTP_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        )
    return _HTTP_SESSION


async def fetch_torn_api(
    endpoint: str,
    selections: str,
    api_key: str,
    torn_id: Optional[int] = None,
    extra_params: Optional[Dict[str, Any]] = None,
) -> dict:
    if torn_id is None:
        url = f"{TORN_API_BASE}/{endpoint}/"
    else:
        url = f"{TORN_API_BASE}/{endpoint}/{torn_id}"

    params = {"selections": selections, "key": api_key}
    if extra_params:
        params.update(extra_params)

    session = await get_session()
    async with session.get(url, params=params) as resp:
        data = await resp.json()

    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        raise TornAPIError(err.get("code", 0), err.get("error", "Unknown error"))

    return data


async def close_api_session() -> None:
    global _HTTP_SESSION
    if _HTTP_SESSION and not _HTTP_SESSION.closed:
        await _HTTP_SESSION.close()
