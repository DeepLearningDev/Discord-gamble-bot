import random as r
import json
import traceback
import time

import hikari, crescent, miru

plugin = crescent.Plugin[hikari.GatewayBot, None]()

from gambling.client_instance import guild_id  # Ensure guild_id is an int
from gambling.points import get_points, update_points

# Global dictionary to store active Blackjack game states.
# Keys are message IDs (as strings) and values are dictionaries holding game state.
GAMES = {}

# Card definitions.
card_ranks = ['Ace', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'Jack', 'Queen', 'King']
card_suits = ["Hearts", "Spades", "Clubs", "Diamonds"]

def draw(amount=1):
    hand = []
    for _ in range(amount):
        rank = r.choice(card_ranks)
        suit = r.choice(card_suits)
        hand.append((rank, suit))
    return hand

def calculate_total(hand):
    total = 0
    aces = 0
    for rank, _ in hand:
        if rank == 'Ace':
            total += 11
            aces += 1
        elif rank in ['Jack', 'Queen', 'King']:
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def hand_to_str(hand):
    return ", ".join(f"{rank} of {suit}" for rank, suit in hand)

def simulate_dealer_hand():
    dealer_hand = draw(2)
    dealer_total = calculate_total(dealer_hand)
    while dealer_total < 17:
        dealer_hand.append(draw(1)[0])
        dealer_total = calculate_total(dealer_hand)
    return dealer_hand, dealer_total

# --- Rewards Helper Function ---
def calculate_rewards(bet: int, outcome: str) -> int:
    """
    Returns the reward amount (positive if points are won, negative if lost).
    Outcome should be one of: "blackjack", "win", "tie", "loss".
    """
    if outcome == "blackjack":
        return bet * 5
    elif outcome == "win":
        return int(bet + (bet / 2))
    elif outcome == "tie":
        return bet
    elif outcome == "loss":
        return -bet
    return 0

# --- Helper Functions ---
def disable_view(view: miru.View) -> list:
    for item in view.children:
        item.disabled = True
    return view.build()

async def send_ephemeral_update(interaction: hikari.ComponentInteraction, content: str, view: miru.View) -> None:
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        content=content,
        components=disable_view(view),
        flags=hikari.MessageFlag.EPHEMERAL
    )

# --- Command and Listeners ---
@plugin.include
@crescent.command(
    name="blackjack",
    description="Play a game of blackjack. Bet at least 10 points.",
    guild=guild_id
)
class Blackjack:
    bet: int = crescent.option(int, "Enter your bet amount (minimum 10 points)")

    async def callback(self, ctx: crescent.Context) -> None:
        if self.bet < 10:
            await ctx.respond("❌ The minimum bet is **10** points.", flags=hikari.MessageFlag.EPHEMERAL)
            return

        user_id = ctx.interaction.user.id
        if get_points(user_id) < self.bet:
            await ctx.respond("❌ You don't have enough points to make that bet!", flags=hikari.MessageFlag.EPHEMERAL)
            return

        # Delete any existing game for this user.
        for existing_game_id, existing_game in list(GAMES.items()):
            if existing_game["user_id"] == user_id:
                try:
                    await ctx.app.rest.delete_message(ctx.interaction.channel_id, int(existing_game_id))
                except Exception:
                    pass
                try:
                    existing_game["view"].stop()
                except Exception:
                    pass
                del GAMES[existing_game_id]

        # Create a view with Hit and Stay buttons.
        view = miru.View(timeout=180)
        view.add_item(miru.Button(style=hikari.ButtonStyle.PRIMARY, label="Hit", custom_id="bj_hit"))
        view.add_item(miru.Button(style=hikari.ButtonStyle.SECONDARY, label="Stay", custom_id="bj_stay"))

        hand = draw(2)
        total = calculate_total(hand)
        content = (
            f"🎲 **Blackjack** 🎲\n\n"
            f"**Bet:** {self.bet} points\n"
            f"**Your Hand:** {hand_to_str(hand)}\n"
            f"**Total:** {total}\n\n"
            "Choose your action:"
        )

        await ctx.respond(content, components=view.build(), flags=hikari.MessageFlag.EPHEMERAL)
        message = await ctx.interaction.fetch_initial_response()
        game_id = str(message.id)
        GAMES[game_id] = {
            "hand": hand,
            "total": total,
            "bet": self.bet,
            "user_id": user_id,
            "view": view
        }
        await view.wait()

@plugin.include
@crescent.event
async def on_component_hit(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not (isinstance(interaction, hikari.ComponentInteraction) and interaction.custom_id == "bj_hit"):
        return

    game_id = str(interaction.message.id)
    if game_id not in GAMES:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ Game not found.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    game = GAMES[game_id]
    if interaction.user.id != game["user_id"]:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ This isn't your game!",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    try:
        new_card = draw(1)[0]
        game["hand"].append(new_card)
        game["total"] = calculate_total(game["hand"])
        content = (
            f"🎲 **Blackjack Update** 🎲\n\n"
            f"**Bet:** {game['bet']} points\n"
            f"**Your Hand:** {hand_to_str(game['hand'])}\n"
            f"**Total:** {game['total']}\n\n"
        )
        # Add Double Down button dynamically after the first hit.
        if len(game["hand"]) > 2 and not any(item.custom_id == "bj_double" for item in game["view"].children):
            game["view"].add_item(miru.Button(style=hikari.ButtonStyle.SUCCESS, label="Double Down", custom_id="bj_double"))

        if game["total"] > 21:
            outcome_key = "loss"
            outcome_text = "❌ **Bust! You lose your bet.**"
            reward = calculate_rewards(game["bet"], outcome_key)
            new_total = get_points(game["user_id"]) + reward
            update_points(game["user_id"], new_total)
            content += f"{outcome_text}\nYou lost **{abs(reward)}** points.\nYour new total: **{new_total}** points."
            await send_ephemeral_update(interaction, content, game["view"])
            del GAMES[game_id]
        elif game["total"] == 21:
            outcome_key = "blackjack"
            outcome_text = "🎉 **Blackjack! You win double your bet!**"
            reward = calculate_rewards(game["bet"], outcome_key)
            new_total = get_points(game["user_id"]) + reward
            update_points(game["user_id"], new_total)
            content += f"{outcome_text}\nYou won **{reward}** points.\nYour new total: **{new_total}** points."
            await send_ephemeral_update(interaction, content, game["view"])
            del GAMES[game_id]
        else:
            content += "Choose your next action:"
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                content=content,
                components=game["view"].build(),
                flags=hikari.MessageFlag.EPHEMERAL
            )
    except Exception:
        traceback.print_exc()
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ An error occurred while processing your action.",
            flags=hikari.MessageFlag.EPHEMERAL
        )

@plugin.include
@crescent.event
async def on_component_stay(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not (isinstance(interaction, hikari.ComponentInteraction) and interaction.custom_id == "bj_stay"):
        return

    game_id = str(interaction.message.id)
    if game_id not in GAMES:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ Game not found.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    game = GAMES[game_id]
    if interaction.user.id != game["user_id"]:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ This isn't your game!",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    try:
        dealer_hand, dealer_total = simulate_dealer_hand()
        dealer_str = hand_to_str(dealer_hand)
        player_total = game["total"]

        if dealer_total > 21:
            outcome_key = "win"
            outcome_text = "🎉 **Dealer busts! You win!**"
        elif dealer_total == player_total:
            outcome_key = "tie"
            outcome_text = "🤝 **Push! It's a tie.**"
        elif dealer_total > player_total:
            outcome_key = "loss"
            outcome_text = "❌ **Dealer wins! You lose your bet.**"
        else:
            outcome_key = "win"
            outcome_text = "🎉 **You win!**"

        reward = calculate_rewards(game["bet"], outcome_key)
        new_total = get_points(game["user_id"]) + reward
        update_points(game["user_id"], new_total)
        content = (
            f"🎲 **Final Results** 🎲\n\n"
            f"**Your Final Hand:** {hand_to_str(game['hand'])}\n"
            f"**Your Total:** {player_total}\n\n"
            f"**Dealer's Hand:** {dealer_str}\n"
            f"**Dealer's Total:** {dealer_total}\n\n"
            f"**Bet:** {game['bet']} points\n"
            f"{outcome_text}\n"
            f"You {'won' if reward > 0 else 'lost' if reward < 0 else 'broke even'}, "
            f"receiving a net change of **{abs(reward)}** points.\n"
            f"Your new total is **{new_total}** points."
        )
        await send_ephemeral_update(interaction, content, game["view"])
        del GAMES[game_id]
    except Exception:
        traceback.print_exc()
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ An error occurred while processing your action.",
            flags=hikari.MessageFlag.EPHEMERAL
        )

@plugin.include
@crescent.event
async def on_component_double(event: hikari.InteractionCreateEvent) -> None:
    interaction = event.interaction
    if not (isinstance(interaction, hikari.ComponentInteraction) and interaction.custom_id == "bj_double"):
        return

    game_id = str(interaction.message.id)
    if game_id not in GAMES:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ Game not found.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    game = GAMES[game_id]
    if interaction.user.id != game["user_id"]:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ This isn't your game!",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    try:
        if len(game["hand"]) <= 2:
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                "❌ Double Down is allowed only after your first hit.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        if get_points(game["user_id"]) < game["bet"] * 2:
            await interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                "❌ You don't have enough points to double down.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        game["bet"] *= 2
        new_card = draw(1)[0]
        game["hand"].append(new_card)
        game["total"] = calculate_total(game["hand"])

        dealer_hand, dealer_total = simulate_dealer_hand()
        dealer_str = hand_to_str(dealer_hand)
        player_total = game["total"]

        if dealer_total > 21:
            outcome_key = "win"
            outcome_text = "🎉 **Dealer busts! You win!**"
        elif dealer_total == player_total:
            outcome_key = "tie"
            outcome_text = "🤝 **Push! It's a tie.**"
        elif dealer_total > player_total:
            outcome_key = "loss"
            outcome_text = "❌ **Dealer wins! You lose your bet.**"
        else:
            outcome_key = "win"
            outcome_text = "🎉 **You win!**"

        reward = calculate_rewards(game["bet"], outcome_key)
        new_total = get_points(game["user_id"]) + reward
        update_points(game["user_id"], new_total)
        content = (
            f"🎲 **Final Results** 🎲\n\n"
            f"**Your Final Hand:** {hand_to_str(game['hand'])}\n"
            f"**Your Total:** {player_total}\n\n"
            f"**Dealer's Hand:** {dealer_str}\n"
            f"**Dealer's Total:** {dealer_total}\n\n"
            f"**Your Doubled Bet:** {game['bet']} points\n"
            f"{outcome_text}\n"
            f"You {'won' if reward > 0 else 'lost' if reward < 0 else 'broke even'}, "
            f"with a net change of **{abs(reward)}** points.\n"
            f"Your new total is **{new_total}** points."
        )
        await send_ephemeral_update(interaction, content, game["view"])
        del GAMES[game_id]
    except Exception:
        traceback.print_exc()
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            "❌ An error occurred while processing your double down action.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
