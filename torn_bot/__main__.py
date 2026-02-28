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

from torn_bot.config import (
    DISCORD_TOKEN,
    FACTION_LEADERBOARD_CHANNEL_ID,
    DAILY_LEADERBOARD_HOUR,
    DAILY_LEADERBOARD_MINUTE,
)
from torn_bot.storage import KeyStorage
from torn_bot.commands import setup_all_commands
from torn_bot.commands.faction_leaderboard_daily import build_faction_leaderboard_daily_message
from torn_bot.services.faction_leaderboard_store import sync_faction_attacks
from torn_bot.services.flight_watch import run_flight_watch_loop

def main():
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN not found in .env")

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    storage = KeyStorage()
    setup_all_commands(tree, storage)

    def log(msg: str) -> None:
        now = datetime.now(tz=LONDON).strftime("%d %m %y %H:%M:%S")
        print(f"{now} {msg}")

    async def get_leaderboard_channel():
        if not FACTION_LEADERBOARD_CHANNEL_ID:
            return None
        channel = client.get_channel(FACTION_LEADERBOARD_CHANNEL_ID)
        if channel is not None:
            return channel
        try:
            return await client.fetch_channel(FACTION_LEADERBOARD_CHANNEL_ID)
        except Exception:
            return None

    async def maybe_post_daily_leaderboard() -> None:
        now = datetime.now(tz=LONDON)
        if (now.hour, now.minute) < (DAILY_LEADERBOARD_HOUR, DAILY_LEADERBOARD_MINUTE):
            return
        api_key = storage.get_global_key("faction")
        if not api_key:
            log("daily leaderboard skipped: no global faction API key")
            return
        channel = await get_leaderboard_channel()
        if channel is None:
            log("daily leaderboard skipped: channel not accessible")
            return
        try:
            msg = await build_faction_leaderboard_daily_message(
                api_key,
                include_backfill_status=False,
                include_no_attacks_line=False,
            )
        except Exception as e:
            log(f"daily leaderboard failed: {e}")
            return
        try:
            msg = "## Daily Summary\n\n" + msg
            await channel.send(msg)
            log(f"daily leaderboard sent to channel {FACTION_LEADERBOARD_CHANNEL_ID}")
        except Exception as e:
            log(f"daily leaderboard send failed: {e}")

    async def run_daily_leaderboard() -> None:
        if not FACTION_LEADERBOARD_CHANNEL_ID:
            log("daily leaderboard skipped: no channel id configured")
            return
        while not client.is_closed():
            now = datetime.now(tz=LONDON)
            next_run = now.replace(
                hour=DAILY_LEADERBOARD_HOUR,
                minute=DAILY_LEADERBOARD_MINUTE,
                second=0,
                microsecond=0,
            )
            if now >= next_run:
                next_run = next_run + timedelta(days=1)
            sleep_s = max(1.0, (next_run - now).total_seconds())
            log(f"daily leaderboard sleeping until {next_run.strftime('%d %m %y %H:%M:%S')}")
            await asyncio.sleep(sleep_s)
            if client.is_closed():
                return
            await maybe_post_daily_leaderboard()

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

    daily_task = None
    flight_task = None

    @client.event
    async def on_ready():
        nonlocal daily_task, flight_task
        await tree.sync()
        if not leaderboard_sync_task.is_running():
            leaderboard_sync_task.start()
        if daily_task is None or daily_task.done():
            daily_task = client.loop.create_task(run_daily_leaderboard())
        if flight_task is None or flight_task.done():
            flight_task = client.loop.create_task(run_flight_watch_loop(client, storage))
        api_key = storage.get_global_key("faction")
        if not api_key:
            log("startup check: no global faction API key set")
        if FACTION_LEADERBOARD_CHANNEL_ID:
            channel = await get_leaderboard_channel()
            if channel is None:
                log(f"startup check: channel {FACTION_LEADERBOARD_CHANNEL_ID} not accessible")
            else:
                log(f"startup check: channel {FACTION_LEADERBOARD_CHANNEL_ID} ok")
        else:
            log("startup check: no daily leaderboard channel configured")
        log(
            "bot ready - "
            f"{client.user} daily_time={DAILY_LEADERBOARD_HOUR:02d}:{DAILY_LEADERBOARD_MINUTE:02d} "
            f"channel_id={FACTION_LEADERBOARD_CHANNEL_ID}"
        )

    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
