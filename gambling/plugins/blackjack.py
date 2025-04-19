import random as r
import json
import traceback
import time

import hikari, crescent, miru

plugin = crescent.Plugin[hikari.GatewayBot, None]()

from gambling.client_instance import guild_id  # Ensure guild_id is an int
from gambling.points import get_points, update_points

# Global dictionary to store active Blackjack game states.
GAMES = {}

# Card definitions.
card_ranks = ['Ace', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'Jack', 'Queen', 'King']
card_suits = ["Hearts", "Spades", "Clubs", "Diamonds"]

def draw(amount=1):
    """Draw 'amount' cards randomly from an infinite deck."""
    hand = []
    for _ in range(amount):
        rank = r.choice(card_ranks)
        suit = r.choice(card_suits)
        hand.append((rank, suit))
    return hand

def calculate_total(hand):
    """Calculate a blackjack hand's total, counting Aces as 11 or 1 as needed."""
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
    """Return a string representation of a hand."""
    return ", ".join(f"{rank} of {suit}" for rank, suit in hand)

def is_blackjack(hand):
    """Check if a given two-card hand is a blackjack."""
    return len(hand) == 2 and calculate_total(hand) == 21

def simulate_dealer_turn(dealer_hand):
    """Dealer reveals the hidden card and hits until total is 17 or more.
       Dealer stands on soft 17 (Ace counted as 11 if it brings total to 17)."""
    total = calculate_total(dealer_hand)
    while total < 17:
        dealer_hand.append(draw(1)[0])
        total = calculate_total(dealer_hand)
    return dealer_hand, total

def build_blackjack_view(can_double: bool) -> list:
    view = miru.View(timeout=180)
    view.add_item(
        miru.Button(
            style=hikari.ButtonStyle.PRIMARY,
            label="Hit",
            custom_id="bj_hit"
        )
    )
    view.add_item(
        miru.Button(
            style=hikari.ButtonStyle.SECONDARY,
            label="Stand",
            custom_id="bj_stand"
        )
    )
    if can_double:
        view.add_item(
            miru.Button(
                style=hikari.ButtonStyle.SUCCESS,
                label="Double Down",
                custom_id="bj_double"
            )
        )
    return view.build()


def classify_win(outcome: str) -> str:
    """Returns a descriptive string based on the outcome."""
    mapping = {
        "blackjack": "Blackjack (3:2 payout)",
        "win": "Win",
        "tie": "Push (tie)",
        "loss": "Loss"
    }
    return mapping.get(outcome, outcome)

@plugin.include
@crescent.command(
    name="blackjack",
    description="Play blackjack! Bet at least 10 points.",
    guild=guild_id
)
class Blackjack:
    bet: int = crescent.option(int, "Enter your bet amount (min 10 points)")

    async def callback(self, ctx: crescent.Context) -> None:
        # Delete any existing game for this user.
        user_id = ctx.interaction.user.id
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

        if self.bet < 10:
            await ctx.respond("❌ The minimum bet is 10 points.", flags=hikari.MessageFlag.EPHEMERAL)
            return

        if get_points(user_id) < self.bet:
            await ctx.respond("❌ You don't have enough points to make that bet!", flags=hikari.MessageFlag.EPHEMERAL)
            return

        # Initial Deal:
        player_hand = draw(2)
        dealer_hand = draw(2)
        dealer_upcard = dealer_hand[0]  # Dealer's upcard is always visible

        # Check for naturals:
        player_blackjack = is_blackjack(player_hand)
        dealer_blackjack = is_blackjack(dealer_hand)

        # Create a view for player's turn (Hit, Stand, Double Down if allowed).
        can_double = (len(player_hand) == 2 and get_points(user_id) >= self.bet * 2)
        view = miru.View(timeout=180)
        view.add_item(miru.Button(style=hikari.ButtonStyle.PRIMARY, label="Hit", custom_id="bj_hit"))
        view.add_item(miru.Button(style=hikari.ButtonStyle.SECONDARY, label="Stand", custom_id="bj_stand"))
        if can_double:
            view.add_item(miru.Button(style=hikari.ButtonStyle.SUCCESS, label="Double Down", custom_id="bj_double"))

        content = (
            "♠️ **Blackjack** ♠️\n\n"
            f"**Bet:** {self.bet} points\n\n"
            f"**Your Hand:** {hand_to_str(player_hand)} | Total: {calculate_total(player_hand)}\n"
            f"**Dealer's Upcard:** {hand_to_str([dealer_upcard])}\n"
        )

        # Natural blackjack check:
        if player_blackjack or dealer_blackjack:
            content += f"**Dealer's Hand:** {hand_to_str(dealer_hand)} (Total: {calculate_total(dealer_hand)})\n\n"
            if player_blackjack and not dealer_blackjack:
                outcome = "blackjack"
                winnings = int(self.bet * 1.5)
                update_points(user_id, get_points(user_id) + winnings)
                content += f"🎉 You got a Blackjack! You win {winnings} points!"
            elif dealer_blackjack and not player_blackjack:
                outcome = "loss"
                update_points(user_id, get_points(user_id) - self.bet)
                content += f"😞 Dealer has a Blackjack. You lose your bet of {self.bet} points."
            else:
                outcome = "tie"
                content += "🤝 It's a push. Your bet is returned."
            content += f"\n\n**New Total:** {get_points(user_id)} points"
            await ctx.respond(content, )
            return

        content += "\nChoose your action:"
        await ctx.respond(content, components=view.build(), )
        message = await ctx.interaction.fetch_initial_response()
        game_id = str(message.id)
        GAMES[game_id] = {
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "bet": self.bet,
            "user_id": user_id,
            "view": view,
            "doubled": False
        }
        await view.wait()

@plugin.include
@crescent.event
async def on_component_blackjack(event: hikari.InteractionCreateEvent) -> None:
    if not isinstance(event.interaction, hikari.ComponentInteraction):
        return
    if event.interaction.custom_id not in ["bj_hit", "bj_stand", "bj_double"]:
        return

    game_id = str(event.interaction.message.id)
    if game_id not in GAMES:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content="❌ Game not found.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    game = GAMES[game_id]
    user_id = game["user_id"]
    if event.interaction.user.id != user_id:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content="❌ This isn't your game!",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    action = event.interaction.custom_id
    player_hand = game["player_hand"]
    dealer_hand = game["dealer_hand"]
    dealer_upcard = dealer_hand[0]
    bet = game["bet"]

    if action == "bj_hit":
        new_card = draw(1)[0]
        player_hand.append(new_card)
        total = calculate_total(player_hand)
        content = (
            "♠️ **Blackjack Update** ♠️\n\n"
            f"**Your Hand:** {hand_to_str(player_hand)} (Total: {total})\n"
            f"**Dealer's Upcard:** {hand_to_str([dealer_upcard])}\n"
        )
        if total > 21:
            update_points(user_id, get_points(user_id) - bet)
            content += f"❌ **Bust!** You exceeded 21 and lost your bet of {bet} points.\n\n"
            content += f"**New Total:** {get_points(user_id)} points"
            await event.interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                content=content,
                
            )
            del GAMES[game_id]
            return
        else:
            content += "Choose your next action:"
            view = build_blackjack_view(can_double=False)
            game["view"] = view
            await event.interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                content=content,
                components=view,
                
            )
    elif action == "bj_double":
        if get_points(user_id) < bet:
            await event.interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                content="❌ Not enough points to double down.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return
        update_points(user_id, get_points(user_id) - bet)
        game["bet"] *= 2
        game["doubled"] = True
        new_card = draw(1)[0]
        player_hand.append(new_card)
        total = calculate_total(player_hand)
        content = (
            "♠️ **Double Down** ♠️\n\n"
            f"**Your Hand:** {hand_to_str(player_hand)} (Total: {total})\n"
        )
        if total > 21:
            update_points(user_id, get_points(user_id) - game["bet"])
            content += f"❌ **Bust!** You exceeded 21 and lost your doubled bet of {game['bet']} points.\n\n"
            content += f"**New Total:** {get_points(user_id)} points"
            await event.interaction.create_initial_response(
                hikari.ResponseType.MESSAGE_UPDATE,
                content=content,
                
            )
            del GAMES[game_id]
            return
        await proceed_dealer_turn(game_id, event.interaction)
    elif action == "bj_stand":
        await proceed_dealer_turn(game_id, event.interaction)

async def proceed_dealer_turn(game_id: str, interaction: hikari.ComponentInteraction) -> None:
    game = GAMES.get(game_id)
    if not game:
        await interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_UPDATE,
            content="❌ Game not found.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return
    dealer_hand = game["dealer_hand"] if "dealer_hand" in game else draw(2)
    if "dealer_hand" not in game:
        game["dealer_hand"] = dealer_hand

    dealer_hand, dealer_total = simulate_dealer_turn(game["dealer_hand"])
    player_total = calculate_total(game["player_hand"])
    content = (
        "♠️ **Dealer's Turn** ♠️\n\n"
        f"**Your Hand:** {hand_to_str(game['player_hand'])} (Total: {player_total})\n"
        f"**Dealer's Hand:** {hand_to_str(dealer_hand)} (Total: {dealer_total})\n\n"
    )
    if dealer_total > 21 or player_total > dealer_total:
        outcome = "win"
        content += f"🎉 You win! You earn a payout of {int(game['bet'] + game['bet'] * 0.5)} points."
        print(f'{game["user_id"]} won at blackjack!')
        update_points(game["user_id"], get_points(game["user_id"]) + int(game["bet"] + game["bet"] * 0.5))
    elif dealer_total == player_total:
        outcome = "tie"
        content += "🤝 It's a push. You get your bet back."
    else:
        outcome = "loss"
        content += f"❌ Dealer wins! You lose your bet of {game['bet']} points."
        update_points(game["user_id"], get_points(game["user_id"]) - game["bet"])
    new_total = get_points(game["user_id"])
    content += f"\n\n**New Total:** {new_total} points"
    await interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_UPDATE,
        content=content
    )
    del GAMES[game_id]
    
