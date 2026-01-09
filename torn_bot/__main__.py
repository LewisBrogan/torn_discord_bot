import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
    LONDON = ZoneInfo("Europe/London")
except Exception:
    LONDON = timezone.utc

from torn_bot.config import DISCORD_TOKEN
from torn_bot.storage import KeyStorage
from torn_bot.commands import setup_all_commands
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
            backfill_done = result.get("backfill_done")
            max_started = result.get("max_started")
            min_started = result.get("min_started")
            backfill_to = result.get("backfill_to")
            tracked_since = result.get("tracked_since")
            added_samples = result.get("added_samples") or []
            duration = (datetime.now(tz=LONDON) - start).total_seconds()
            log(
                "leaderboard sync ok: "
                f"added={added} backfill_done={backfill_done} "
                f"max_started={max_started} min_started={min_started} "
                f"backfill_to={backfill_to} tracked_since={tracked_since} "
                f"duration_s={duration:.2f}"
            )
            if added_samples:
                sample_strs = []
                for s in added_samples:
                    name = s.get("attacker_name") or "?"
                    started_ts = s.get("started") or 0
                    started_str = (
                        datetime.fromtimestamp(started_ts, tz=timezone.utc)
                        .astimezone(LONDON)
                        .strftime("%Y-%m-%d %H:%M:%S")
                        if started_ts
                        else "unknown"
                    )
                    sample_strs.append(
                        f"attack_id={s.get('attack_id')} attacker={name}({s.get('attacker_id')}) started={started_str}"
                    )
                log("leaderboard sync added_samples: " + ", ".join(sample_strs))
        except Exception as e:
            duration = (datetime.now(tz=LONDON) - start).total_seconds()
            log(f"leaderboard sync failed: {e} duration_s={duration:.2f}")

    @client.event
    async def on_ready():
        await tree.sync()
        if not leaderboard_sync_task.is_running():
            leaderboard_sync_task.start()
        log(f"bot ready - {client.user}")

    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
