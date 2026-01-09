import asyncio
import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    LONDON = ZoneInfo("Europe/London")
except Exception:
    LONDON = timezone.utc

from torn_bot.config import DISCORD_TOKEN, FACTION_LEADERBOARD_CHANNEL_ID
from torn_bot.storage import KeyStorage
from torn_bot.commands import setup_all_commands
from torn_bot.commands.faction_leaderboard_daily import build_faction_leaderboard_daily_message
from torn_bot.services.faction_leaderboard_store import sync_faction_attacks

def main():
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN not found in .env")

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    storage = KeyStorage()
    setup_all_commands(tree, storage)

    def log(msg: str) -> None:
        now = datetime.now(tz=LONDON).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{now} {msg}")

    async def run_midnight_leaderboard() -> None:
        if not FACTION_LEADERBOARD_CHANNEL_ID:
            log("midnight leaderboard skipped: no channel id configured")
            return
        while not client.is_closed():
            now = datetime.now(tz=LONDON)
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sleep_s = max(1.0, (next_midnight - now).total_seconds())
            log(f"midnight leaderboard sleeping until {next_midnight.strftime('%Y-%m-%d %H:%M:%S')}")
            await asyncio.sleep(sleep_s)
            if client.is_closed():
                return
            api_key = storage.get_global_key("faction")
            if not api_key:
                log("midnight leaderboard skipped: no global faction API key")
                continue
            try:
                msg = await build_faction_leaderboard_daily_message(api_key)
            except Exception as e:
                log(f"midnight leaderboard failed: {e}")
                continue
            try:
                msg = "## Midnight Announcement - Daily\n\n" + msg
                channel = client.get_channel(FACTION_LEADERBOARD_CHANNEL_ID)
                if channel is None:
                    channel = await client.fetch_channel(FACTION_LEADERBOARD_CHANNEL_ID)
                await channel.send(msg)
                log(f"midnight leaderboard sent to channel {FACTION_LEADERBOARD_CHANNEL_ID}")
            except Exception as e:
                log(f"midnight leaderboard send failed: {e}")

    @tasks.loop(hours=1)
    async def leaderboard_sync_task():
        start = datetime.now(tz=LONDON)
        api_key = storage.get_global_key("faction")
        if not api_key:
            log("leaderboard sync skipped: no global faction API key")
            return
        try:
            result = await sync_faction_attacks(api_key)
            added = result.get("added")
            duration = (datetime.now(tz=LONDON) - start).total_seconds()
            log(
                "leaderboard sync ok: "
                f"added={added} duration_s={duration:.2f}"
            )
        except Exception as e:
            duration = (datetime.now(tz=LONDON) - start).total_seconds()
            log(f"leaderboard sync failed: {e} duration_s={duration:.2f}")

    midnight_task = None

    @client.event
    async def on_ready():
        nonlocal midnight_task
        await tree.sync()
        if not leaderboard_sync_task.is_running():
            leaderboard_sync_task.start()
        if midnight_task is None or midnight_task.done():
            midnight_task = client.loop.create_task(run_midnight_leaderboard())
        log(f"bot ready - {client.user}")

    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
