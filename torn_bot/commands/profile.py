from discord import app_commands
import discord

from torn_bot.api.torn import fetch_torn_api, TornAPIError
from torn_bot.storage import KeyStorage


def setup_profile_commands(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(name="profile", description="show a torn profile")
    @app_commands.describe(player_id="player id to look up (leave blank for yourself)")
    async def profile(interaction: discord.Interaction, player_id: int = None):
        await interaction.response.defer(ephemeral=False)

        api_key = storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send(
                "you need to set your api key first with /setapi\n\nget your key from https://www.torn.com/preferences.php#tab=api",
                ephemeral=True
            )
            return

        try:
            data = await fetch_torn_api("user", "profile", api_key, player_id)

            name = data.get("name", "Unknown")
            pid = data.get("player_id", 0)
            level = data.get("level", 0)
            rank = data.get("rank", "Unknown")
            age = data.get("age", 0)

            status = data.get("status", {})
            status_state = status.get("state", "Unknown")
            status_desc = status.get("description", "")

            life = data.get("life", {})
            life_current = life.get("current", 0)
            life_max = life.get("maximum", 0)

            last_action = data.get("last_action", {})
            last_rel = last_action.get("relative", "Unknown")

            faction = data.get("faction", {})
            faction_name = faction.get("faction_name") or "None"
            faction_pos = faction.get("position", "")

            job = data.get("job", {})
            company = job.get("company_name") or job.get("job") or "Unemployed"

            awards = data.get("awards", 0)
            friends = data.get("friends", 0)
            enemies = data.get("enemies", 0)

            status_line = f"{status_state} - {status_desc}" if status_desc else status_state
            faction_line = f"{faction_name} ({faction_pos})" if (faction_pos and faction_name != "None") else faction_name

            embed = discord.Embed(
                title=f"{name} [{pid}]",
                url=f"https://www.torn.com/profiles.php?XID={pid}",
                color=discord.Color.dark_grey()
            )

            embed.add_field(name="level", value=level, inline=True)
            embed.add_field(name="rank", value=rank, inline=True)
            embed.add_field(name="age", value=f"{age:,} days", inline=True)

            embed.add_field(name="status", value=status_line, inline=True)
            embed.add_field(name="life", value=f"{life_current:,} / {life_max:,}", inline=True)
            embed.add_field(name="last active", value=last_rel, inline=True)

            embed.add_field(name="faction", value=faction_line, inline=True)
            embed.add_field(name="job", value=company, inline=True)
            embed.add_field(name="awards", value=f"{awards:,}", inline=True)

            embed.add_field(name="friends", value=f"{friends:,}", inline=True)
            embed.add_field(name="enemies", value=f"{enemies:,}", inline=True)

            await interaction.followup.send(embed=embed)

        except TornAPIError as e:
            msg = f"something went wrong - {e.message}"
            if e.code in [1, 2, 10, 13, 18]:
                msg += "\n\nyour api key might be invalid, try /setapi again"
            await interaction.followup.send(msg, ephemeral=True)
