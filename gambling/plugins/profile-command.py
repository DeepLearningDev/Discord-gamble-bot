import hikari, crescent

plugin = crescent.Plugin[hikari.GatewayBot, None]()

from gambling.client_instance import guild_id  # Ensure guild_id is an int
from gambling.profile import get_profile, update_profile  # Profile functions

COLOR_CHOICES = [
    ("Blue", "0x1E90FF"),
    ("Red", "0xFF4500"),
    ("Green", "0x32CD32"),
    ("Purple", "0x800080"),
    ("Gold", "0xFFD700"),
    ("Pink", "0xFF69B4"),
    ("Orange", "0xFFA500"),
    ("Yellow", "0xFFFF00"),
    ("Teal", "0x008080"),
    ("Cyan", "0x00FFFF"),
    ("Magenta", "0xFF00FF"),
    ("Lime", "0x00FF00")
]

@plugin.include
@crescent.command(
    name="profile",
    description="Display your profile info and optionally update your color.",
    guild=guild_id
)
class Profile:
    # Optional color option; if provided, update the profile's color.
    color: str = crescent.option(
        str,
        "Choose a profile color (optional)",
        choices=COLOR_CHOICES,
        default=""
    )

    async def callback(self, ctx: crescent.Context) -> None:
        user = ctx.interaction.user
        profile_data = get_profile(user.id)

        # If a new color is provided, update the profile.
        if self.color and self.color.strip() != "":
            profile_data["color"] = self.color
            update_profile(user.id, profile_data)

        # Use stored color or default if not set.
        color_hex = profile_data.get("color", "0x1E90FF")
        color_int = int(color_hex, 16)

        inventory = profile_data.get("inventory", [])
        inventory_str = ", ".join(inventory) if inventory else "None"
        
        achievements = profile_data.get("achievements", [])
        achievements_str = ", ".join(achievements) if achievements else "None"

        # Set the embed title: if the profile has a title, append it.
        if profile_data.get("title"):
            title = f"{user.display_name} the {profile_data['title']}"
        else:
            title = user.display_name

        embed = hikari.Embed(
            title=f"{title}",
            description="A snapshot of your achievements and stats.",
            color=color_int
        )
        embed.set_thumbnail(user.avatar_url)
        embed.add_field(name="Points", value=str(profile_data.get("points", 0)), inline=True)
        embed.add_field(name="Blackjack Wins", value=str(profile_data.get("wins_blackjack", 0)), inline=True)
        embed.add_field(name="Prediction Wins", value=str(profile_data.get("wins_predi", 0)), inline=True)
        embed.add_field(name="Inventory", value=inventory_str, inline=False)
        embed.add_field(name="Achievements", value=achievements_str, inline=False)
        embed.set_footer(text="Customize your profile color with the /profile color command")

        await ctx.respond(embed=embed, flags=hikari.MessageFlag.EPHEMERAL)
