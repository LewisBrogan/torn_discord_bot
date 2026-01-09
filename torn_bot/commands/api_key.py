from discord import app_commands
import discord

from torn_bot.api.torn import fetch_torn_api, TornAPIError
from torn_bot.storage import KeyStorage


def setup_api_key_commands(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(name="setapi", description="save your torn api key")
    @app_commands.describe(api_key="your torn api key")
    async def setapi(interaction: discord.Interaction, api_key: str):
        await interaction.response.defer(ephemeral=True)
        try:
            data = await fetch_torn_api("user", "basic", api_key)
            storage.store_key(interaction.user.id, api_key)

            player_name = data.get("name", "Unknown")
            player_id = data.get("player_id", 0)

            await interaction.followup.send(
                f"saved, verified as {player_name} [{player_id}]",
                ephemeral=True
            )
        except TornAPIError as e:
            await interaction.followup.send(
                f"that key didn't work - {e.message}\n\nget your api key from https://www.torn.com/preferences.php#tab=api",
                ephemeral=True
            )

    @tree.command(name="deleteapi", description="delete your api key")
    async def deleteapi(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if storage.delete_key(interaction.user.id):
            await interaction.followup.send("done, api key removed", ephemeral=True)
        else:
            await interaction.followup.send("you don't have an api key saved", ephemeral=True)
