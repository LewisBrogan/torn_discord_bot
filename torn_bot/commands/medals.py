from discord import app_commands
import discord

from torn_bot.api.torn import fetch_torn_api, TornAPIError
from torn_bot.storage import KeyStorage


def setup_medals_commands(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(name="medals", description="check what medals a player has")
    @app_commands.describe(torn_id="the player's torn id")
    async def medals(interaction: discord.Interaction, torn_id: int):
        await interaction.response.defer(ephemeral=False)

        api_key = storage.get_key(interaction.user.id)
        if not api_key:
            await interaction.followup.send("you need to set your api key first with /setapi", ephemeral=True)
            return

        try:
            user_data = await fetch_torn_api("user", "medals,basic", api_key, torn_id)
            torn_data = await fetch_torn_api("torn", "medals", api_key)

            player_name = user_data.get("name", "Unknown")
            medal_ids = user_data.get("medals_awarded", []) or []
            all_medals = torn_data.get("medals", {}) or {}

            if not medal_ids:
                await interaction.followup.send(f"{player_name} [{torn_id}] has no medals")
                return

            medals_by_type = {}
            for mid in medal_ids:
                m = all_medals.get(str(mid))
                if not m:
                    continue
                mtype = m.get("type", "Other")
                mname = m.get("name", f"Unknown ({mid})")
                medals_by_type.setdefault(mtype, []).append(mname)

            embed = discord.Embed(
                title=f"{player_name} [{torn_id}] - {len(medal_ids)} medals",
                url=f"https://www.torn.com/profiles.php?XID={torn_id}",
                color=discord.Color.dark_grey()
            )

            field_count = 0
            for medal_type, names in sorted(medals_by_type.items()):
                if field_count >= 25:
                    break
                value = "\n".join(f"- {n}" for n in names)
                if len(value) > 1024:
                    value = value[:1020] + "..."
                embed.add_field(name=f"{medal_type} ({len(names)})", value=value, inline=False)
                field_count += 1

            await interaction.followup.send(embed=embed)

        except TornAPIError as e:
            await interaction.followup.send(f"couldn't fetch data - {e.message}", ephemeral=True)
