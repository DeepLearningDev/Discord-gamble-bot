import random
from typing import List

import hikari, crescent, miru

plugin = crescent.Plugin[hikari.GatewayBot, None]()

from gambling.client_instance import guild_id  # Ensure guild_id is an int
from gambling.points import get_points, update_points  # External points functions

# Allowed bets in increasing order.
ALLOWED_BETS: List[int] = [10, 25, 50, 100, 250, 500, 1000]

# Global dictionary to store active Slot Machine game states.
SLOT_GAMES = {}

class SlotMachine:
    def __init__(self):
        self.symbols = ['🍒', '🍋', '🍊', '🍉', '🔔', '💰']
        self.weights = [1, 1, 1, 1, .7, .5]
        self.rows = 3
        self.cols = 3

    def spin(self, bet: int) -> List[List[str]]:
        return [random.choices(self.symbols, weights=self.weights, k=self.cols) for _ in range(self.rows)]

    def check_wins(self, grid: List[List[str]], bet: int) -> int:
        rows = len(grid)
        cols = len(grid[0]) if grid else 0
        winning_amount = 0
        # Adjusted payouts: lower than before.
        payouts = {
            '🍒': int(1.4 * bet),
            '🍋': int(1.8 * bet),
            '🍊': int(2.5 * bet),
            '🍉': int(3 * bet),
            '🔔': int(5 * bet),
            '💰': int(50 * bet)
        }
        # Check horizontal wins (each full row)
        for row in grid:
            if len(set(row)) == 1:
                winning_amount += payouts[row[0]]
        # Check vertical wins (each column)
        for c in range(cols):
            column = [grid[r][c] for r in range(rows)]
            if len(set(column)) == 1:
                winning_amount += payouts[column[0]]
        # Check diagonal wins on any 3 contiguous columns:
        # Diagonal (top-left to bottom-right)
        for start in range(cols - 2):
            if grid[0][start] == grid[1][start+1] == grid[2][start+2]:
                winning_amount += payouts[grid[0][start]]
        # Diagonal (bottom-left to top-right)
        for start in range(cols - 2):
            if grid[2][start] == grid[1][start+1] == grid[0][start+2]:
                winning_amount += payouts[grid[2][start]]
        return int(winning_amount)

def format_grid(grid: List[List[str]]) -> str:
    left_margin = " " * 11  # Adjust this number for more/less left space.
    # Create each row string by joining symbols with " | "
    row_strings = [" | ".join(row) for row in grid]
    # Determine the maximum width of the row strings.
    max_width = max((len(row) for row in row_strings), default=0)
    # Center each row inside vertical bars.
    centered_rows = [f"| {row.center(max_width)} |" for row in row_strings]
    # Create top and bottom borders that span the entire width.
    border = left_margin + "-" * (max_width + 7)
    bottom_border = left_margin + "-" * (max_width + 7)
    # Combine the borders and centered rows with the left margin.
    grid_output = "\n".join(left_margin + row for row in centered_rows)
    return f"{border}\n{grid_output}\n{bottom_border}"

def build_slots_view(current_bet: int) -> list:
    view = miru.View()
    view.add_item(
        miru.Button(
            style=hikari.ButtonStyle.SECONDARY,
            emoji="⬆️",
            custom_id="slots_increase"
        )
    )
    view.add_item(
        miru.Button(
            style=hikari.ButtonStyle.SUCCESS,
            label="Spin",
            custom_id="slots_spin"
        )
    )
    view.add_item(
        miru.Button(
            style=hikari.ButtonStyle.SECONDARY,
            emoji="⬇️",
            
            custom_id="slots_decrease"
        )
    )
    return view.build()

def classify_win(winnings: int, bet: int) -> str:
    """Classify the win type based on the total winnings relative to the bet.
    
    The thresholds are set to reflect combo wins:
      - Ratio < 2: Small win
      - Ratio from 2 up to 3.5: Large win
      - Ratio from 3.5 up to 5: Huge win
      - Ratio from 5 up to 10: Massive win
      - Ratio from 10 up to 20: Small jackpot
      - Ratio 20 or above: Large jackpot
    """
    if winnings == 0:
        return "No win"
    ratio = winnings / bet
    if ratio < 2:
        return "Small Win"
    elif ratio < 3.5:
        return "Large Win"
    elif ratio < 5:
        return "Huge Win"
    elif ratio < 10:
        return "Massive Win"
    elif ratio < 20:
        return "Small Jackpot"
    else:
        return "Jackpot, you're giga lucky"

@plugin.include
@crescent.command(
    name="slots",
    description="Try your luck on the slot machine. Adjust your bet and spin!",
    guild=guild_id
)
class Slots:
    async def callback(self, ctx: crescent.Context) -> None:
        user_id = ctx.interaction.user.id
        current_points = get_points(user_id)
        base_bet = ALLOWED_BETS[0]
        if current_points < base_bet:
            await ctx.respond("❌ You don't have enough points to play.")
            return

        # Create a new SlotMachine instance (but do not spin yet)
        slot_machine = SlotMachine()

        # Build the interface message (initially, no spin result is shown)
        content = (
            "🎰 **Slot Machine** 🎰\n"
            f"**Base Bet:** {base_bet} points\n\n"
            "Press **Spin** to start the game.\n"
            "Use **Increase Bet** or **Decrease Bet** to adjust your wager."
        )
        view_components = build_slots_view(base_bet)
        await ctx.respond(content, components=view_components)
        message = await ctx.interaction.fetch_initial_response()
        game_id = str(message.id)
        SLOT_GAMES[game_id] = {
            "slot_machine": slot_machine,
            "current_bet": base_bet,
            "user_id": user_id,
            "message_id": game_id,
            "grid": None  # Will store the latest spun grid.
        }

@plugin.include
@crescent.event
async def on_component_interaction_slots(event: hikari.InteractionCreateEvent) -> None:
    if not isinstance(event.interaction, hikari.ComponentInteraction):
        return
    if event.interaction.custom_id not in ["slots_spin", "slots_increase", "slots_decrease"]:
        return

    game_id = str(event.interaction.message.id)
    if game_id not in SLOT_GAMES:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content="❌ Game not found.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    game = SLOT_GAMES[game_id]
    user_id = game["user_id"]
    if event.interaction.user.id != user_id:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content="❌ This isn't your game.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    current_bet = game["current_bet"]
    action = event.interaction.custom_id

    # For bet adjustments, we'll include the previously spun grid if it exists.
    grid = game.get("grid")
    grid_text = f"\n{format_grid(grid):^50}\n\n" if grid else "\n\n"
    new_total = get_points(user_id)  # Current total points after any bets

    if action == "slots_spin":
        if get_points(user_id) < current_bet:
            await event.interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                content="❌ Not enough points for that bet.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return
        # Deduct the bet.
        update_points(user_id, get_points(user_id) - current_bet)
        slot_machine = game["slot_machine"]
        grid = slot_machine.spin(current_bet)
        game["grid"] = grid  # Store the spun grid in the game state.
        winnings = slot_machine.check_wins(grid, current_bet)
        if winnings > 0:
            win_type = classify_win(winnings, current_bet)
            win_out = f"+**{winnings}** points"
            outcome = f"🎉  **{win_type:^23}**  🎉\n {win_out:^40}"
            update_points(user_id, get_points(user_id) + winnings)
        else:
            outcome = f"💀  **No win this time**  💀"
        new_total = get_points(user_id)
        content = (
            "🎰 **Lets Go Gambling** 🎰\n"
            f"{outcome:^26}"
            f"\n{format_grid(grid)}\n"
            f"*Bet*: **{current_bet}** points\n"
            f"*New Total*: **{new_total}** points"
        )
        components = build_slots_view(current_bet)
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content=content,
            components=components,
            
        )
    elif action == "slots_increase":
        current_index = ALLOWED_BETS.index(current_bet)
        if current_index < len(ALLOWED_BETS) - 1:
            new_bet = ALLOWED_BETS[current_index + 1]
        else:
            new_bet = current_bet
        game["current_bet"] = new_bet
        new_total = get_points(user_id)
        content = (
            "🎰 **Lets Go Gambling** 🎰\n"
            f"Your bet is now **{new_bet}** points."
            f"{grid_text}"
            f"Press **Spin** to play with the new bet.\n"
            f"*New Total*: **{new_total}** points"
        )
        components = build_slots_view(new_bet)
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content=content,
            components=components,
            
        )
    elif action == "slots_decrease":
        current_index = ALLOWED_BETS.index(current_bet)
        if current_index > 0:
            new_bet = ALLOWED_BETS[current_index - 1]
        else:
            new_bet = current_bet
        game["current_bet"] = new_bet
        new_total = get_points(user_id)
        content = (
            "🎰 **Lets Go Gambling** 🎰\n"
            f"Your bet is now **{new_bet}** points."
            f"{grid_text}"
            f"Press **Spin** to play with the new bet.\n"
            f"*New Total*: **{new_total}** points"
        )
        components = build_slots_view(new_bet)
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content=content,
            components=components,
            
        )
