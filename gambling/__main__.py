import asyncio
import os
import time
import logging
import hikari
import crescent

from gambling.client_instance import bot, client, guild_id
from gambling.points import get_points, add_point

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("hikari")
logger2 = logging.getLogger("crescent")
logger.setLevel(logging.DEBUG)
logger2.setLevel(logging.DEBUG)

@client.include
@crescent.command(name="ping", description="Check bot latency", guild=guild_id)
async def ping(ctx: crescent.Context) -> None:
    start = time.perf_counter()
    await asyncio.sleep(0)
    end = time.perf_counter()
    latency = (end - start) * 1000
    await ctx.respond(f"Pong! `{latency:.2f}ms`")

@bot.listen(hikari.MessageCreateEvent)
async def on_message(event: hikari.MessageCreateEvent) -> None:
    if event.is_bot or event.guild_id is None:
        return
    add_point(event.author.id)
    print(f"{event.author.username} now has {get_points(event.author.id)} points.")

@client.include
@crescent.command(name="points", description="Check your points", guild=guild_id)
async def points(ctx: crescent.Context) -> None:
    await ctx.respond(f"You have {get_points(ctx.interaction.user.id)} points!")

if __name__ == "__main__":
    if os.name == "nt":
        import winloop
        asyncio.set_event_loop_policy(winloop.EventLoopPolicy())
    bot.run()
