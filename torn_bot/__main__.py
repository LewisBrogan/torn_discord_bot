import discord
from discord import app_commands

from torn_bot.config import DISCORD_TOKEN
from torn_bot.storage import KeyStorage
from torn_bot.commands import setup_all_commands

def main():
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN not found in .env")

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    storage = KeyStorage()
    setup_all_commands(tree, storage)

    @client.event
    async def on_ready():
        await tree.sync()
        print(f"bot ready - {client.user}")

    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
