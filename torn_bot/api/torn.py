from __future__ import annotations
from typing import Optional, Dict, Any
import aiohttp
from torn_bot.config import TORN_API_BASE


class TornAPIError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Torn API Error {code}: {message}")


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

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()

    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        raise TornAPIError(err.get("code", 0), err.get("error", "Unknown error"))

    return data
