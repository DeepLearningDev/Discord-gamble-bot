# client_instance.py
import os
import hikari
import crescent

guild_id = int(os.environ["GUILD_ID"])

bot = hikari.GatewayBot(
    token=os.environ["TOKEN"],
    intents=hikari.Intents.ALL
)

client = crescent.Client(bot, allow_unknown_interactions=True)
client.plugins.load_folder("gambling.plugins")
