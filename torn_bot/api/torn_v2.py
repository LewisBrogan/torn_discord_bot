from __future__ import annotations
import aiohttp
from typing import Optional, Dict, Any
import asyncio

TORN_V2_BASE = "https://api.torn.com/v2"

_HTTP_SESSION: aiohttp.ClientSession | None = None


class TornAPIError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"torn API error {code}: {message}")
        self.code = code
        self.message = message


async def get_session() -> aiohttp.ClientSession:
    global _HTTP_SESSION
    if _HTTP_SESSION is None or _HTTP_SESSION.closed:
        _HTTP_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        )
    return _HTTP_SESSION


async def fetch_torn_v2(
    path: str,
    *,
    api_key: str,
    params: Optional[Dict[str, Any]] = None,
) -> dict:
    session = await get_session()

    url = f"{TORN_V2_BASE}{path}"
    q = dict(params or {})
    q["key"] = api_key

    backoffs = [0.5, 1.0, 2.0]
    last_err: Exception | None = None

    for i in range(len(backoffs) + 1):
        try:
            async with session.get(url, params=q) as resp:
                if resp.status == 429 or resp.status >= 500:
                    raise TornAPIError(resp.status, f"http {resp.status}")
                data = await resp.json()
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                raise TornAPIError(int(err.get("code", 0)), err.get("error", "unknwn error"))
            return data
        except TornAPIError as e:
            last_err = e
            if i >= len(backoffs):
                break
            await asyncio.sleep(backoffs[i])
        except Exception as e:
            last_err = e
            if i >= len(backoffs):
                break
            await asyncio.sleep(backoffs[i])

    if isinstance(last_err, TornAPIError):
        raise last_err
    raise TornAPIError(0, f"request failed: {last_err}")


async def close_v2_session() -> None:
    global _HTTP_SESSION
    if _HTTP_SESSION and not _HTTP_SESSION.closed:
        await _HTTP_SESSION.close()
