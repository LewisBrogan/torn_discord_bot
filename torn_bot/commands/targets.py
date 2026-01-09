from discord import app_commands
import discord
import aiohttp

from torn_bot.api.torn import fetch_torn_api
from torn_bot.storage import KeyStorage
from torn_bot.config import TORN_API_BASE


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
        for torn_id in target_ids:
            try:
                profile_data = await fetch_torn_api("user", "profile", api_key, torn_id)

                stats_url = f"{TORN_API_BASE}/user/{torn_id}"
                stats_params = {
                    "selections": "personalstats",
                    "stat": "xantaken,refills,statenhancersused,energydrinkused",
                    "key": api_key
                }
                async with aiohttp.ClientSession() as session:
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
