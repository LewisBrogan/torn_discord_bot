from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import defaultdict

import discord
from discord import app_commands

try:
    from zoneinfo import ZoneInfo
    LONDON = ZoneInfo("Europe/London")
except Exception:
    LONDON = timezone.utc

from torn_bot.storage import KeyStorage
from torn_bot.api.torn_v2 import TornAPIError
from torn_bot.services.faction_attacks import (
    fetch_today_faction_attacks,
    fetch_faction_attacks_since,
    fmt_time_london,
    result_tag,
)
from torn_bot.services.name_resolver import resolve_names


def setup_global_attacks_command(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(
        name="global_faction_attacks",
        description="Show today's faction attacks with useful summaries (London time)."
    )
    async def global_faction_attacks(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        api_key = storage.get_global_key("faction") or storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send(
                "no API key available. Owners must run /set_global_faction_api first",
                ephemeral=True
            )
            return

        try:
            today_attacks = await fetch_today_faction_attacks(api_key, page_limit=8, per_page=100)
        except TornAPIError as e:
            await interaction.followup.send(f"Couldn't fetch attacks: {e.message}", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Error fetching attacks: {e}", ephemeral=True)
            return

        today_str = datetime.now(tz=LONDON).strftime("%d/%m/%y")

        if not today_attacks:
            await interaction.followup.send(f"**Faction attacks today ({today_str})**\n\nNo attacks found.")
            return

        def safe_str(x) -> str:
            if x is None:
                return ""
            return x.strip() if isinstance(x, str) else str(x)

        def to_float(x) -> float:
            try:
                return float(x or 0)
            except Exception:
                return 0.0

        def fmt_signed(x: float) -> str:
            return f"{x:+.2f}"

        def attacker_id(a: dict) -> int:
            try:
                return int((a.get("attacker") or {}).get("id", 0) or 0)
            except Exception:
                return 0

        def defender_id(a: dict) -> int:
            try:
                return int((a.get("defender") or {}).get("id", 0) or 0)
            except Exception:
                return 0

        def extract_ids(items: list[dict]) -> set[int]:
            out: set[int] = set()
            for a in items:
                ai = attacker_id(a)
                di = defender_id(a)
                if ai:
                    out.add(ai)
                if di:
                    out.add(di)
            return out

        def profile_link(name: str, tid: int) -> str:
            return f"[{name} [{tid}]](https://www.torn.com/profiles.php?XID={tid})"

        hosp: list[dict] = []
        mugs: list[dict] = []
        other: list[dict] = []

        total_rg = 0.0
        total_rl = 0.0

        for a in today_attacks:
            res_l = safe_str(a.get("result", "")).lower()

            rg = to_float(a.get("respect_gain", 0))
            rl = to_float(a.get("respect_loss", 0))
            total_rg += rg
            total_rl += rl

            if "hospital" in res_l:
                hosp.append(a)
            elif "mug" in res_l:
                mugs.append(a)
            else:
                other.append(a)

        mugs_sorted = sorted(mugs, key=lambda x: to_float(x.get("respect_gain", 0)), reverse=True)
        other_sorted = sorted(other, key=lambda x: to_float(x.get("respect_gain", 0)), reverse=True)

        now_utc = datetime.now(timezone.utc)
        since_24h = int((now_utc - timedelta(hours=24)).timestamp())
        since_7d = int((now_utc - timedelta(days=7)).timestamp())

        try:
            attacks_24h = await fetch_faction_attacks_since(api_key, since_utc=since_24h, page_limit=12, per_page=100)
        except Exception:
            attacks_24h = []

        try:
            attacks_7d = await fetch_faction_attacks_since(api_key, since_utc=since_7d, page_limit=60, per_page=100)
        except Exception:
            attacks_7d = []

        def top_respect_earners(attacks: list[dict], top_n: int = 5) -> list[tuple[int, float]]:
            totals = defaultdict(float)
            for a in attacks:
                aid = attacker_id(a)
                if not aid:
                    continue
                totals[aid] += to_float(a.get("respect_gain", 0))
            ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
            return ranked[:top_n]

        top24 = top_respect_earners(attacks_24h, top_n=5)
        top7d = top_respect_earners(attacks_7d, top_n=5)

        ids_to_resolve = set()
        ids_to_resolve |= extract_ids(hosp)
        ids_to_resolve |= extract_ids(mugs_sorted[:10])
        ids_to_resolve |= extract_ids(other_sorted[:10])
        ids_to_resolve |= {tid for tid, _ in top24}
        ids_to_resolve |= {tid for tid, _ in top7d}

        seeded: dict[int, str] = {}
        for group in (today_attacks, attacks_24h, attacks_7d):
            for a in group:
                for side in ("attacker", "defender"):
                    p = a.get(side) or {}
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

        def fmt_person(tid_val) -> str:
            try:
                tid = int(tid_val or 0)
            except Exception:
                tid = 0
            if tid <= 0:
                return "`?`"
            nm = name_map.get(tid)
            if nm:
                return profile_link(nm, tid)
            return f"`{tid}`"

        def fmt_attack_line(a: dict) -> str:
            st = int(a.get("started", 0) or 0)
            t = fmt_time_london(st)[:5]

            tag = result_tag(safe_str(a.get("result", "")))
            aid = a.get("id", "?")

            rg = to_float(a.get("respect_gain", 0))
            rl = to_float(a.get("respect_loss", 0))

            a_id = attacker_id(a)
            d_id = defender_id(a)

            return (
                f"{t} `[{tag}]` `#{aid}` `{rg:+.2f}/{-rl:+.2f}` "
                f"{fmt_person(a_id)} -> {fmt_person(d_id)}"
            )

        def build_section(title: str, rows: list[str]) -> str:
            if not rows:
                return ""
            return "**" + title + "**\n" + "\n".join(rows)

        msg1_lines: list[str] = []
        msg1_lines.append(f"**Faction attacks today ({today_str})**")
        msg1_lines.append("")
        msg1_lines.append("**Summary**")
        msg1_lines.append(f"• Total: {len(today_attacks)}")
        msg1_lines.append(f"• Hospitals: {len(hosp)}")
        msg1_lines.append(f"• Mugs: {len(mugs)}")
        msg1_lines.append(f"• Respect: {fmt_signed(total_rg)} / {fmt_signed(-total_rl)}")
        msg1_lines.append("")
        msg1_lines.append("**Top respect earners**")

        if top24:
            msg1_lines.append("• 24 hours:")
            for tid, val in top24:
                nm = name_map.get(tid)
                who = profile_link(nm, tid) if nm else f"`{tid}`"
                msg1_lines.append(f"  - {who}: `{val:+.2f}`")
        else:
            msg1_lines.append("• 24 hours: (no data)")

        if top7d:
            msg1_lines.append("• 7 days:")
            for tid, val in top7d:
                nm = name_map.get(tid)
                who = profile_link(nm, tid) if nm else f"`{tid}`"
                msg1_lines.append(f"  - {who}: `{val:+.2f}`")
        else:
            msg1_lines.append("• 7 days: (no data)")

        await interaction.followup.send("\n".join(msg1_lines)[:1900])

        sections: list[str] = []

        if hosp:
            sections.append(build_section("Hospitals", [fmt_attack_line(a) for a in hosp]))

        if mugs_sorted:
            sections.append(build_section("Mugs (top 10 by respect gain)", [fmt_attack_line(a) for a in mugs_sorted[:10]]))

        if other_sorted:
            sections.append(build_section("Other (top 10 by respect gain)", [fmt_attack_line(a) for a in other_sorted[:10]]))

        MAX = 1900
        for sec in sections:
            if not sec:
                continue

            if len(sec) <= MAX:
                await interaction.followup.send(sec)
                continue

            lines = sec.split("\n")
            cur = ""
            for ln in lines:
                if len(cur) + len(ln) + 1 > MAX:
                    await interaction.followup.send(cur.rstrip())
                    cur = ""
                cur += ln + "\n"
            if cur.strip():
                await interaction.followup.send(cur.rstrip())
