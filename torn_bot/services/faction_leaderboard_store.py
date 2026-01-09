from __future__ import annotations

from typing import Optional, Dict, Any
import json

from torn_bot.db import get_conn, init_db
from torn_bot.api.torn_v2 import fetch_torn_v2
from torn_bot.services.faction_attacks import fetch_faction_attacks_since


RECENT_SYNC_LOOKBACK_SECONDS = 60 * 60
RECENT_SYNC_PAGE_LIMIT = 3
BACKFILL_PAGE_LIMIT = 3


def _get_meta(key: str) -> Optional[str]:
    conn = get_conn()
    cur = conn.execute("SELECT value FROM faction_leaderboard_meta WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def _set_meta(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO faction_leaderboard_meta (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def _apply_attack(
    attacker_id: int,
    started: int,
    attack_id: int,
    *,
    ended: Optional[int],
    result: Optional[str],
    is_mug: int,
    is_hosp: int,
    respect_gain: float,
    respect_loss: float,
    mugged: float,
    attacker_name: Optional[str],
    defender_id: Optional[int],
    defender_name: Optional[str],
    raw_json: Optional[str],
) -> bool:
    conn = get_conn()
    cur = conn.execute("SELECT 1 FROM faction_attacks_seen WHERE attack_id = ?", (attack_id,))
    if cur.fetchone():
        conn.execute(
            """
            UPDATE faction_attacks_seen
            SET attacker_id = COALESCE(?, attacker_id),
                started = COALESCE(?, started),
                ended = COALESCE(?, ended),
                result = COALESCE(?, result),
                respect_gain = COALESCE(?, respect_gain),
                respect_loss = COALESCE(?, respect_loss),
                attacker_name = COALESCE(?, attacker_name),
                defender_id = COALESCE(?, defender_id),
                defender_name = COALESCE(?, defender_name),
                raw_json = COALESCE(?, raw_json)
            WHERE attack_id = ?
            """,
            (
                attacker_id,
                started,
                ended,
                result,
                respect_gain,
                respect_loss,
                attacker_name,
                defender_id,
                defender_name,
                raw_json,
                attack_id,
            ),
        )
        conn.commit()
        conn.close()
        return False

    conn.execute(
        """
        INSERT INTO faction_attacks_seen
            (
                attack_id,
                attacker_id,
                started,
                ended,
                result,
                respect_gain,
                respect_loss,
                attacker_name,
                defender_id,
                defender_name,
                raw_json
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attack_id,
            attacker_id,
            started,
            ended,
            result,
            respect_gain,
            respect_loss,
            attacker_name,
            defender_id,
            defender_name,
            raw_json,
        ),
    )

    conn.execute(
        """
        INSERT INTO faction_leaderboard_totals
            (attacker_id, attacks, mugs, hosp, respect_gain, respect_loss, mugged, best_mug)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(attacker_id) DO UPDATE SET
            attacks = attacks + excluded.attacks,
            mugs = mugs + excluded.mugs,
            hosp = hosp + excluded.hosp,
            respect_gain = respect_gain + excluded.respect_gain,
            respect_loss = respect_loss + excluded.respect_loss,
            mugged = mugged + excluded.mugged,
            best_mug = CASE
                WHEN excluded.best_mug > best_mug THEN excluded.best_mug
                ELSE best_mug
            END
        """,
        (
            attacker_id,
            1,
            int(is_mug),
            int(is_hosp),
            respect_gain,
            respect_loss,
            mugged,
            mugged,
        ),
    )
    conn.commit()
    conn.close()
    return True


async def sync_faction_attacks(api_key: str) -> Dict[str, Any]:
    init_db()

    last_sync = _get_meta("leaderboard_last_sync_started")
    since_utc = max(0, int(last_sync) - RECENT_SYNC_LOOKBACK_SECONDS) if last_sync else 0
    added_samples: list[dict[str, Any]] = []
    sample_limit = 5

    def to_float(x) -> float:
        try:
            return float(x or 0)
        except Exception:
            return 0.0

    def extract_mugged(a: dict) -> float:
        mugged = 0.0
        for key in ("money_mugged", "mugged", "money", "cash"):
            if key not in a:
                continue
            val = a.get(key)
            if isinstance(val, dict):
                for sub in ("amount", "value", "money"):
                    if sub in val:
                        mugged = to_float(val.get(sub, 0))
                        break
            else:
                mugged = to_float(val)
            if mugged:
                break
        return mugged

    def apply_attack(a: dict) -> bool:
        try:
            attack_id = int(a.get("id", 0) or 0)
            started = int(a.get("started", 0) or 0)
            ended = int(a.get("ended", 0) or 0)
            attacker = a.get("attacker") or {}
            defender = a.get("defender") or {}
            attacker_id = int(attacker.get("id", 0) or 0)
            defender_id = int(defender.get("id", 0) or 0)
        except Exception:
            return False

        if not attack_id or not attacker_id or not started:
            return False

        def clean_str(val) -> Optional[str]:
            if val is None:
                return None
            if isinstance(val, str):
                s = val.strip()
                return s if s else None
            return str(val)

        res_l = str(a.get("result", "") or "").lower()
        is_mug = 1 if "mug" in res_l else 0
        is_hosp = 1 if "hospital" in res_l else 0
        mugged = extract_mugged(a) if is_mug else 0.0

        return _apply_attack(
            attacker_id,
            started,
            attack_id,
            ended=ended or None,
            result=clean_str(a.get("result")),
            is_mug=is_mug,
            is_hosp=is_hosp,
            respect_gain=to_float(a.get("respect_gain", 0)),
            respect_loss=to_float(a.get("respect_loss", 0)),
            mugged=mugged,
            attacker_name=clean_str(attacker.get("name")),
            defender_id=defender_id or None,
            defender_name=clean_str(defender.get("name")),
            raw_json=json.dumps(a, separators=(",", ":"), ensure_ascii=True),
        )

    added = 0
    max_started = 0
    min_started = 0

    recent_attacks = await fetch_faction_attacks_since(
        api_key,
        since_utc=since_utc,
        page_limit=RECENT_SYNC_PAGE_LIMIT,
        per_page=100,
    )

    for a in recent_attacks:
        if apply_attack(a):
            added += 1
            started = int(a.get("started", 0) or 0)
            if started > max_started:
                max_started = started
            if min_started == 0 or started < min_started:
                min_started = started
            if len(added_samples) < sample_limit:
                attacker = a.get("attacker") or {}
                added_samples.append(
                    {
                        "attack_id": int(a.get("id", 0) or 0),
                        "attacker_id": int(attacker.get("id", 0) or 0),
                        "attacker_name": attacker.get("name"),
                        "started": started,
                    }
                )

    backfill_done = _get_meta("leaderboard_backfill_done") == "1"
    backfill_to = _get_meta("leaderboard_backfill_to")
    to_param = int(backfill_to) if backfill_to else None

    if not backfill_done:
        for _ in range(BACKFILL_PAGE_LIMIT):
            params = {"limit": 100, "sort": "DESC"}
            if to_param is not None:
                params["to"] = to_param
            data = await fetch_torn_v2("/faction/attacksfull", api_key=api_key, params=params)
            attacks = data.get("attacks") or []
            if not attacks:
                backfill_done = True
                break

            for a in attacks:
                if apply_attack(a):
                    added += 1
                    started = int(a.get("started", 0) or 0)
                    if started > max_started:
                        max_started = started
                    if min_started == 0 or started < min_started:
                        min_started = started
                    if len(added_samples) < sample_limit:
                        attacker = a.get("attacker") or {}
                        added_samples.append(
                            {
                                "attack_id": int(a.get("id", 0) or 0),
                                "attacker_id": int(attacker.get("id", 0) or 0),
                                "attacker_name": attacker.get("name"),
                                "started": started,
                            }
                        )

            to_param = int(attacks[-1].get("ended", 0) or 0)
            if not to_param:
                backfill_done = True
                break

    if max_started:
        _set_meta("leaderboard_last_sync_started", str(max_started))
    if min_started:
        existing = _get_meta("leaderboard_tracked_since")
        if not existing or min_started < int(existing):
            _set_meta("leaderboard_tracked_since", str(min_started))

    if backfill_done:
        _set_meta("leaderboard_backfill_done", "1")
    if to_param:
        _set_meta("leaderboard_backfill_to", str(to_param))

    return {
        "added": added,
        "backfill_done": backfill_done,
        "max_started": max_started or None,
        "min_started": min_started or None,
        "backfill_to": to_param,
        "tracked_since": _get_meta("leaderboard_tracked_since"),
        "added_samples": added_samples,
    }


def get_overall_leaderboard() -> Dict[str, Any]:
    conn = get_conn()

    def top_row(col: str):
        cur = conn.execute(
            f"SELECT attacker_id, {col} FROM faction_leaderboard_totals ORDER BY {col} DESC LIMIT 1"
        )
        return cur.fetchone()

    most_attacks = top_row("attacks")
    most_mugs = top_row("mugs")
    most_hosp = top_row("hosp")
    most_rg = top_row("respect_gain")
    best_mug = top_row("best_mug")

    cur = conn.execute("SELECT SUM(mugged) FROM faction_leaderboard_totals")
    total_mugged = cur.fetchone()[0] or 0

    tracked_since = _get_meta("leaderboard_tracked_since")
    backfill_done = _get_meta("leaderboard_backfill_done") == "1"
    conn.close()

    return {
        "most_attacks": most_attacks,
        "most_mugs": most_mugs,
        "most_hosp": most_hosp,
        "most_rg": most_rg,
        "best_mug": best_mug,
        "total_mugged": float(total_mugged or 0),
        "tracked_since": tracked_since,
        "backfill_done": backfill_done,
    }
