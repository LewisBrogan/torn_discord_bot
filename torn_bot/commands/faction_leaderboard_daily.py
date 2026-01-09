from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord import app_commands

try:
    from zoneinfo import ZoneInfo
    LONDON = ZoneInfo("Europe/London")
except Exception:
    LONDON = timezone.utc

from torn_bot.storage import KeyStorage
from torn_bot.api.torn_v2 import TornAPIError
from torn_bot.services.faction_attacks import fetch_today_faction_attacks
from torn_bot.services.faction_leaderboard_store import (
    sync_faction_attacks,
    get_overall_leaderboard,
)
from torn_bot.services.name_resolver import resolve_names


async def build_faction_leaderboard_daily_message(api_key: str) -> str:
    today_attacks = []
    today_error = None
    sync_error = None

    try:
        today_attacks = await fetch_today_faction_attacks(api_key, page_limit=4, per_page=100)
    except TornAPIError as e:
        today_error = e.message
    except Exception as e:
        today_error = str(e)

    try:
        await sync_faction_attacks(api_key)
    except TornAPIError as e:
        sync_error = e.message
    except Exception as e:
        sync_error = str(e)

    today_str = datetime.now(tz=LONDON).strftime("%d/%m/%y")

    if not today_attacks and not sync_error and not today_error:
        return f"**Faction leaderboard today ({today_str})**\n\nNo attacks found."

    def safe_str(x) -> str:
        if x is None:
            return ""
        return x.strip() if isinstance(x, str) else str(x)

    def to_float(x) -> float:
        try:
            return float(x or 0)
        except Exception:
            return 0.0

    def attacker_id(a: dict) -> int:
        try:
            return int((a.get("attacker") or {}).get("id", 0) or 0)
        except Exception:
            return 0

    def mug_amount(a: dict) -> float:
        for key in ("money_mugged", "mugged", "money", "cash"):
            if key not in a:
                continue
            val = a.get(key)
            if isinstance(val, dict):
                for sub in ("amount", "value", "money"):
                    if sub in val:
                        return to_float(val.get(sub, 0))
                return 0.0
            return to_float(val)
        return 0.0

    stats = defaultdict(lambda: {
        "attacks": 0,
        "mugs": 0,
        "hosp": 0,
        "rg": 0.0,
        "rl": 0.0,
        "mugged": 0.0,
    })

    total_mugged = 0.0
    best_mug_amount = 0.0
    best_mug_id = 0

    for a in today_attacks:
        aid = attacker_id(a)
        if not aid:
            continue

        res_l = safe_str(a.get("result", "")).lower()
        if "mug" in res_l:
            stats[aid]["mugs"] += 1
            amt = mug_amount(a)
            stats[aid]["mugged"] += amt
            total_mugged += amt
            if amt > best_mug_amount:
                best_mug_amount = amt
                best_mug_id = aid
        if "hospital" in res_l:
            stats[aid]["hosp"] += 1

        stats[aid]["attacks"] += 1
        stats[aid]["rg"] += to_float(a.get("respect_gain", 0))
        stats[aid]["rl"] += to_float(a.get("respect_loss", 0))

    if not stats and not today_error:
        return f"**Faction leaderboard today ({today_str})**\n\nNo attacks found."

    def top_by(key: str):
        return max(stats.items(), key=lambda kv: kv[1][key])

    most_attacks_id, most_attacks = top_by("attacks")
    most_mugs_id, most_mugs = top_by("mugs")
    most_hosp_id, most_hosp = top_by("hosp")
    most_rg_id, most_rg = top_by("rg")

    overall = get_overall_leaderboard()
    overall_ids = set()
    for key in ("most_attacks", "most_mugs", "most_hosp", "most_rg", "best_mug"):
        row = overall.get(key)
        if row and row[0]:
            overall_ids.add(int(row[0]))

    ids_to_resolve = {
        most_attacks_id,
        most_mugs_id,
        most_hosp_id,
        most_rg_id,
    }
    if best_mug_id:
        ids_to_resolve.add(best_mug_id)
    ids_to_resolve |= overall_ids

    seeded: dict[int, str] = {}
    for a in today_attacks:
        p = a.get("attacker") or {}
        try:
            tid = int(p.get("id", 0) or 0)
        except Exception:
            continue
        nm = safe_str(p.get("name", ""))
        if tid and nm and tid not in seeded:
            seeded[tid] = nm

    resolved = await resolve_names(api_key, ids_to_resolve)
    name_map = dict(resolved)
    name_map.update(seeded)

    def profile_link(tid: int) -> str:
        if tid <= 0:
            return "`?`"
        nm = name_map.get(tid)
        if nm:
            return f"[{nm} [{tid}]](https://www.torn.com/profiles.php?XID={tid})"
        return f"`{tid}`"

    def fmt_row(row, fmt: str) -> str:
        if not row:
            return "`?`"
        return fmt.format(profile_link(int(row[0])), row[1])

    overall_lines = [
        "**Faction Leaderboard Overall**",
        "",
        f"Most attacks: {fmt_row(overall.get('most_attacks'), '{} - `{}`')}",
        f"Most mugs: {fmt_row(overall.get('most_mugs'), '{} - `{}`')}",
        f"Most respect gained: {fmt_row(overall.get('most_rg'), '{} - `{:+.2f}`')}",
        "",
    ]
    tracked_since = overall.get("tracked_since")
    if tracked_since:
        try:
            ts = int(tracked_since)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(LONDON)
            overall_lines.append(f"Tracked since: {dt.strftime('%d/%m/%y %H:%M')}")
        except Exception:
            overall_lines.append(f"Tracked since: {tracked_since}")
    if overall.get("backfill_done"):
        overall_lines.append("Backfill from faction data complete")
    else:
        overall_lines.append("Backfill status (in progress)")

    if today_error:
        today_lines = [
            f"**Faction Leaderboard Today ({today_str})**",
            "",
            f"Today data unavailable: {today_error}",
        ]
    else:
        today_lines = [
            f"**Faction Leaderboard Today ({today_str})**",
            "",
            f"Most attacks: {profile_link(most_attacks_id)} - `{most_attacks['attacks']}`",
            f"Most mugs: {profile_link(most_mugs_id)} - `{most_mugs['mugs']}`",
            f"Most hospitals: {profile_link(most_hosp_id)} - `{most_hosp['hosp']}`",
            f"Most respect gained: {profile_link(most_rg_id)} - `{most_rg['rg']:+.2f}`",
        ]

    if sync_error:
        overall_lines.append("")
        overall_lines.append(f"Sync note: {sync_error}")

    msg_lines = overall_lines + [""] + today_lines

    return "\n".join(msg_lines)[:1900]


def setup_faction_leaderboard_daily_commands(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(
        name="faction_leaderboard_daily",
        description="Daily faction leaderboard from today's attacks (London time)."
    )
    async def faction_leaderboard_daily(interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=False)
        except discord.NotFound:
            return

        api_key = storage.get_global_key("faction") or storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send(
                "no API key available. Owners must run /set_global_faction_api first",
                ephemeral=True
            )
            return

        try:
            msg = await build_faction_leaderboard_daily_message(api_key)
        except Exception as e:
            await interaction.followup.send(f"Error building leaderboard: {e}", ephemeral=True)
            return

        await interaction.followup.send(msg)
