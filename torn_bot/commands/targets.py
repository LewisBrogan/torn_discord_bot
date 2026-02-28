from discord import app_commands
import discord
import aiohttp
import re
import textwrap

from torn_bot.api.torn import fetch_torn_api
from torn_bot.storage import KeyStorage
from torn_bot.config import TORN_API_BASE


NETWORTH_MEDAL_TYPES = {"NTW", "NWT", "Networth", "Net Worth"}
NETWORTH_MEDAL_ORDER = [
    "Apprentice",
    "Entrepreneur",
    "Executive",
    "Millionaire",
    "Multimillionaire",
    "Capitalist",
    "Plutocrat",
]
NETWORTH_MEDAL_RANK = {
    name: index for index, name in enumerate(NETWORTH_MEDAL_ORDER)
}
NETWORTH_DESC_RE = re.compile(r"\$([0-9,]+)")


def _parse_networth_amount(desc: object) -> int | None:
    if not isinstance(desc, str):
        return None
    match = NETWORTH_DESC_RE.search(desc)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _format_amount_short(amount: int) -> str:
    if amount >= 1_000_000_000_000:
        return f"{amount // 1_000_000_000_000}T+"
    if amount >= 1_000_000_000:
        return f"{amount // 1_000_000_000}B+"
    if amount >= 1_000_000:
        return f"{amount // 1_000_000}M+"
    if amount >= 1_000:
        return f"{amount // 1_000}K+"
    return f"{amount}+"


def _highest_networth_medal(medal_ids: list, medals_by_id: dict) -> tuple[str | None, int | None]:
    if medal_ids and not medals_by_id:
        return None, None
    best_name = None
    best_amount = None
    best_rank = None

    for mid in medal_ids:
        medal = medals_by_id.get(str(mid))
        if not medal:
            continue
        medal_type = medal.get("type")
        if medal_type not in NETWORTH_MEDAL_TYPES:
            continue
        name = medal.get("name") or "Unknown"
        amount = _parse_networth_amount(medal.get("description"))
        if amount is not None:
            if best_amount is None or amount > best_amount:
                best_amount = amount
                best_name = name
            continue
        rank = NETWORTH_MEDAL_RANK.get(name)
        if rank is not None:
            if best_amount is None and (best_rank is None or rank > best_rank):
                best_rank = rank
                best_name = name
        elif best_amount is None and best_rank is None:
            best_name = name

    return best_name, best_amount


def _networth_sort_key(name: str | None, amount: int | None) -> tuple[int, int]:
    if amount is not None:
        return 2, amount
    if name and name in NETWORTH_MEDAL_RANK:
        return 1, NETWORTH_MEDAL_RANK[name]
    return 0, -1


def _to_int(value: object, default: int = -1) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _trim_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def _sanitize_cell(text: object) -> str:
    return (
        str(text)
        .replace("\n", " ")
        .replace("`", "'")
        .replace("|", "/")
        .strip()
    )


TABLE_COLUMNS = [
    ("Name [ID]", 26, "left"),
    ("Lvl", 3, "right"),
    ("Age", 3, "right"),
    ("Networth medal", 22, "left"),
    ("Last online", 14, "left"),
    ("Notes", 28, "left"),
]
WRAP_COLUMNS = {5}


def _table_border() -> str:
    return "+" + "+".join("-" * (width + 2) for _, width, _ in TABLE_COLUMNS) + "+\n"


def _table_row(values: list) -> str:
    cells = []
    for value, (_, width, align) in zip(values, TABLE_COLUMNS):
        text = _trim_text(_sanitize_cell(value), width)
        if align == "right":
            cells.append(f" {text:>{width}} ")
        else:
            cells.append(f" {text:<{width}} ")
    return "|" + "|".join(cells) + "|\n"


def _wrap_text(text: str, width: int) -> list[str]:
    if width <= 0:
        return [""]
    if not text:
        return [""]
    return textwrap.wrap(
        text,
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]


def _table_rows(values: list) -> list[str]:
    wrapped_cells = []
    max_lines = 1
    for idx, (value, (_, width, align)) in enumerate(zip(values, TABLE_COLUMNS)):
        text = _sanitize_cell(value)
        if idx in WRAP_COLUMNS:
            lines = _wrap_text(text, width)
        else:
            lines = [_trim_text(text, width)]
        wrapped_cells.append((lines, width, align))
        max_lines = max(max_lines, len(lines))

    row_lines = []
    for line_idx in range(max_lines):
        cells = []
        for lines, width, align in wrapped_cells:
            text = lines[line_idx] if line_idx < len(lines) else ""
            if align == "right":
                cells.append(f" {text:>{width}} ")
            else:
                cells.append(f" {text:<{width}} ")
        row_lines.append("|" + "|".join(cells) + "|\n")
    return row_lines


def setup_targets_commands(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(name="targets_add", description="add players to your target list")
    @app_commands.describe(torn_ids="player ids separated by commas, e.g. 1234,5678,9012")
    async def targets_add(interaction: discord.Interaction, torn_ids: str):
        await interaction.response.defer(ephemeral=False)

        api_key = storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send("you need to set your api key first with /setapi", ephemeral=True)
            return

        id_list = [x.strip() for x in torn_ids.split(",") if x.strip()]
        added, already_exists, failed = [], [], []

        for id_str in id_list:
            try:
                torn_id = int(id_str)
                data = await fetch_torn_api("user", "basic", api_key, torn_id)
                player_name = data.get("name", "Unknown")

                if storage.add_target(interaction.user.id, torn_id):
                    added.append(f"{player_name} [{torn_id}]")
                else:
                    already_exists.append(f"{player_name} [{torn_id}]")
            except ValueError:
                failed.append(f"invalid id: {id_str}")
            except Exception as e:
                failed.append(f"[{id_str}]: {e}")

        parts = []
        if added:
            parts.append(f"**added {len(added)}:** {', '.join(added)}")
        if already_exists:
            parts.append(f"**already in list ({len(already_exists)}):** {', '.join(already_exists)}")
        if failed:
            parts.append(f"**failed ({len(failed)}):** {', '.join(failed)}")

        out = "\n".join(parts) if parts else "nothing to add"
        if len(out) > 1900:
            out = f"**added:** {len(added)} | **already:** {len(already_exists)} | **failed:** {len(failed)}"
        await interaction.followup.send(out)

    @tree.command(name="targets_remove", description="remove players from your target list")
    @app_commands.describe(torn_ids="player ids separated by commas, e.g. 1234,5678,9012")
    async def targets_remove(interaction: discord.Interaction, torn_ids: str):
        await interaction.response.defer(ephemeral=False)

        id_list = [x.strip() for x in torn_ids.split(",") if x.strip()]
        removed, not_found = [], []

        for id_str in id_list:
            try:
                torn_id = int(id_str)
                if storage.remove_target(interaction.user.id, torn_id):
                    removed.append(str(torn_id))
                else:
                    not_found.append(str(torn_id))
            except ValueError:
                not_found.append(id_str)

        parts = []
        if removed:
            parts.append(f"**removed:** {', '.join(removed)}")
        if not_found:
            parts.append(f"**not in list:** {', '.join(not_found)}")

        await interaction.followup.send("\n".join(parts) if parts else "nothing to remove")

    @tree.command(name="targets_clear", description="remove all targets from your list")
    async def targets_clear(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        count = storage.clear_targets(interaction.user.id)
        await interaction.followup.send(f"cleared {count} targets" if count else "you don't have any targets")

    @tree.command(name="targets", description="show your target list with live stats")
    async def targets(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        api_key = storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send("you need to set your api key first with /setapi", ephemeral=True)
            return

        target_ids = storage.get_targets(interaction.user.id)
        if not target_ids:
            await interaction.followup.send("you don't have any targets, add some with /targets_add")
            return

        rows = []
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for torn_id in target_ids:
                try:
                    profile_data = await fetch_torn_api("user", "profile", api_key, torn_id)

                    stats_url = f"{TORN_API_BASE}/user/{torn_id}"
                    stats_params = {
                        "selections": "personalstats",
                        "stat": "xantaken,refills,statenhancersused,energydrinkused",
                        "key": api_key
                    }
                    async with session.get(stats_url, params=stats_params) as resp:
                        stats_data = await resp.json()

                    pstats = stats_data.get("personalstats", {}) or {}

                    name = profile_data.get("name", "Unknown")
                    level = profile_data.get("level", 0)
                    age = profile_data.get("age", 0)

                    status_state = (profile_data.get("status") or {}).get("state", "?")
                    life = profile_data.get("life", {}) or {}
                    life_current = life.get("current", 0)
                    life_max = life.get("maximum", 0)

                    last_rel = (profile_data.get("last_action") or {}).get("relative", "?")

                    xanax = pstats.get("xantaken", 0) or 0
                    refills = pstats.get("refills", 0) or 0
                    se_used = pstats.get("statenhancersused", 0) or 0
                    ecans = pstats.get("energydrinkused", 0) or 0

                    status_icon = {
                        "Okay": "OK",
                        "Hospital": "HOSP",
                        "Jail": "JAIL",
                        "Traveling": "TRVL"
                    }.get(status_state, "?")

                    rows.append({
                        "name": name,
                        "id": torn_id,
                        "lvl": level,
                        "age": age,
                        "status": status_icon,
                        "life": f"{life_current}/{life_max}",
                        "xan": xanax,
                        "ref": refills,
                        "ecan": ecans,
                        "se": se_used,
                        "last": last_rel
                    })

                except Exception:
                    rows.append({
                        "name": "???",
                        "id": torn_id,
                        "lvl": "?",
                        "age": "?",
                        "status": "ERR",
                        "life": "?",
                        "xan": "?",
                        "ref": "?",
                        "ecan": "?",
                        "se": "?",
                        "last": "error"
                    })

        header = "```\n"
        header += f"{'NAME':<15} {'LVL':>4} {'AGE':>5} {'ST':>4} {'LIFE':>11} {'XAN':>5} {'REF':>4} {'ECAN':>5} {'LAST':<12}\n"
        header += "-" * 78 + "\n"

        lines = []
        for r in rows:
            nm = str(r["name"])
            name = nm[:14] if len(nm) > 14 else nm
            last = str(r["last"])[:11]
            lines.append(
                f"{name:<15} {r['lvl']:>4} {r['age']:>5} {r['status']:>4} {r['life']:>11} {r['xan']:>5} {r['ref']:>4} {r['ecan']:>5} {last:<12}"
            )

        table = header + "\n".join(lines) + "\n```"
        if len(table) <= 1900:
            await interaction.followup.send(table)
        else:
            await interaction.followup.send(table[:1900] + "\n```")
            await interaction.followup.send("```\n" + table[1900:][:1900])

    vip_targets = app_commands.Group(
        name="vip_targets",
        description="manage the shared VIP target list"
    )
    tree.add_command(vip_targets)

    @vip_targets.command(name="add", description="add a player to your VIP targets")
    @app_commands.describe(torn_id="player id", notes="optional notes")
    async def vip_targets_add(
        interaction: discord.Interaction,
        torn_id: int,
        notes: str = None
    ):
        await interaction.response.defer(ephemeral=False)

        api_key = storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send("you need to set your api key first with /setapi", ephemeral=True)
            return

        clean_notes = None
        if notes is not None:
            clean_notes = " ".join(notes.split()).strip()
            if not clean_notes:
                clean_notes = None

        try:
            data = await fetch_torn_api("user", "basic", api_key, torn_id)
            player_name = data.get("name", "Unknown")
        except Exception as e:
            await interaction.followup.send(f"couldn't fetch player data - {e}", ephemeral=True)
            return

        result = storage.add_vip_target(torn_id, clean_notes)
        if result == "added":
            await interaction.followup.send(f"added to shared VIP list: {player_name} [{torn_id}]")
        elif result == "updated":
            await interaction.followup.send(f"updated notes in shared VIP list: {player_name} [{torn_id}]")
        else:
            await interaction.followup.send(f"already in shared VIP list: {player_name} [{torn_id}]")

    @vip_targets.command(name="remove", description="remove a player from your VIP targets")
    @app_commands.describe(torn_id="player id")
    async def vip_targets_remove(interaction: discord.Interaction, torn_id: int):
        await interaction.response.defer(ephemeral=False)

        if storage.remove_vip_target(torn_id):
            await interaction.followup.send(f"removed from shared VIP list: {torn_id}")
        else:
            await interaction.followup.send(f"not in shared VIP list: {torn_id}")

    @vip_targets.command(name="list", description="show your VIP targets with live stats")
    async def vip_targets_list(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        api_key = storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send("you need to set your api key first with /setapi", ephemeral=True)
            return

        vip_targets = storage.get_vip_targets()
        if not vip_targets:
            await interaction.followup.send("no shared VIP targets yet, add some with /vip_targets add")
            return

        rows = []
        medals_by_id = {}
        try:
            torn_medals = await fetch_torn_api("torn", "medals", api_key)
            medals_by_id = torn_medals.get("medals", {}) or {}
        except Exception:
            medals_by_id = {}

        for torn_id, notes in vip_targets:
            try:
                profile_data = await fetch_torn_api("user", "profile,medals", api_key, torn_id)
                name = profile_data.get("name", "Unknown")
                level = profile_data.get("level", 0)
                age = profile_data.get("age", 0)
                last_rel = (profile_data.get("last_action") or {}).get("relative", "?")
                medal_ids = profile_data.get("medals_awarded", []) or []
                badge_name, badge_amount = _highest_networth_medal(medal_ids, medals_by_id)
                if medal_ids and not medals_by_id:
                    badge_text = "?"
                elif not badge_name:
                    badge_text = "-"
                elif badge_amount is None:
                    badge_text = badge_name
                else:
                    badge_text = f"{badge_name} ({_format_amount_short(badge_amount)})"
                networth_sort = _networth_sort_key(badge_name, badge_amount)
            except Exception:
                name = "???"
                level = "?"
                age = "?"
                last_rel = "error"
                badge_text = "?"
                networth_sort = (0, -1)

            name_id = f"{name} [{torn_id}]"
            last = last_rel
            note = notes or "-"

            rows.append({
                "name": name_id,
                "id": torn_id,
                "lvl": level,
                "age": age,
                "badge": badge_text,
                "last": last,
                "notes": note,
                "networth_sort": networth_sort,
                "age_sort": _to_int(age, -1),
            })

        rows.sort(
            key=lambda r: (r["networth_sort"][0], r["networth_sort"][1], r["age_sort"]),
            reverse=True,
        )

        border = _table_border()
        header = border + _table_row([c[0] for c in TABLE_COLUMNS]) + border
        lines = []
        for r in rows:
            lines.extend(
                _table_rows([r["name"], r["lvl"], r["age"], r["badge"], r["last"], r["notes"]])
            )

        messages = []
        current = "```\n" + header
        for line in lines:
            if len(current) + len(line) + len(border) + 4 > 1900:
                current += border + "```"
                messages.append(current)
                current = "```\n" + header + line
            else:
                current += line
        if current != "```\n" + header:
            current += border + "```"
            messages.append(current)

        await interaction.followup.send(f"**Shared VIP targets ({len(rows)})**")
        for msg in messages:
            await interaction.followup.send(msg)
