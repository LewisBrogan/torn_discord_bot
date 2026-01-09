import discord
from discord import app_commands

from torn_bot.storage import KeyStorage
from torn_bot.api.torn_v2 import fetch_torn_v2, TornAPIError
from torn_bot.config import is_owner


def setup_global_keys_commands(tree: app_commands.CommandTree, storage: KeyStorage):

    @tree.command(
        name="set_global_faction_api",
        description="Owner only: set the shared faction API key."
    )
    @app_commands.describe(api_key="Faction-capable Torn API key")
    async def set_global_faction_api(interaction: discord.Interaction, api_key: str):
        await interaction.response.defer(ephemeral=True)

        if not is_owner(interaction.user.id):
            await interaction.followup.send("not allowed.", ephemeral=True)
            return

        try:
            await fetch_torn_v2(
                "/faction/attacksfull",
                api_key=api_key,
                params={"limit": 1, "sort": "DESC"}
            )
        except TornAPIError as e:
            await interaction.followup.send(
                f"key rejected by Torn: {e.message}",
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.followup.send(
                f"unexpected error verifying key: {e}",
                ephemeral=True
            )
            return

        storage.store_global_key("faction", api_key)
        await interaction.followup.send(
            "saved. global faction key updated (encrypted).",
            ephemeral=True
        )

    @tree.command(
        name="delete_global_faction_api",
        description="Owner only: delete the shared faction API key."
    )
    async def delete_global_faction_api(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not is_owner(interaction.user.id):
            await interaction.followup.send("not allowed.", ephemeral=True)
            return

        if storage.delete_global_key("faction"):
            await interaction.followup.send(
                "deleted. global faction key removed.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "no global faction key was set.",
                ephemeral=True
            )
