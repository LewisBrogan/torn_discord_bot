from datetime import datetime, timezone

import discord
from discord import app_commands

from torn_bot.api.torn_v2 import TornAPIError, fetch_torn_v2
from torn_bot.storage import KeyStorage


def setup_faction_inactive_commands(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(
        name="faction_inactive",
        description="List faction members inactive for 24 hours or more."
    )
    async def faction_inactive(interaction: discord.Interaction):
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
            data = await fetch_torn_v2("/faction/members", api_key=api_key)
        except TornAPIError as e:
            await interaction.followup.send(f"Couldn't fetch faction members: {e.message}", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Error fetching faction members: {e}", ephemeral=True)
            return

        members = data.get("members") or {}
        now_ts = int(datetime.now(timezone.utc).timestamp())
        threshold = 24 * 60 * 60

        inactive = []
        def coerce_member(item):
            if isinstance(item, dict):
                return item
            return {}

        if isinstance(members, dict):
            iterable = [coerce_member(v) for v in members.values()]
        elif isinstance(members, list):
            iterable = [coerce_member(v) for v in members]
        else:
            iterable = []

        for info in iterable:
            try:
                tid = int(info.get("id", 0) or 0)
            except Exception:
                tid = 0

            last_action = info.get("last_action") or {}
            last_ts = int(last_action.get("timestamp", 0) or 0)
            if not last_ts:
                continue

            if now_ts - last_ts >= threshold:
                name = info.get("name", "Unknown")
                rel = last_action.get("relative", "?")
                inactive.append((last_ts, tid, name, rel))

        inactive.sort(key=lambda row: row[0])

        header_lines = [
            f"**Total inactive members (24 hours):** {len(inactive)} / {len(members)}",
        ]

        if not inactive:
            await interaction.followup.send("\n".join(header_lines + ["", "No inactive members! 8)"]))
            return

        def profile_link(name: str, tid: int) -> str:
            return f"[{name} [{tid}]](https://www.torn.com/profiles.php?XID={tid})"

        lines = [
            f"• {profile_link(name, tid)} - {rel}"
            for _, tid, name, rel in inactive
        ]

        MAX = 1900
        cur = "\n".join(header_lines) + "\n"
        for line in lines:
            if len(cur) + len(line) + 1 > MAX:
                await interaction.followup.send(cur.rstrip())
                cur = ""
            cur += line + "\n"
        if cur.strip():
            await interaction.followup.send(cur.rstrip())
