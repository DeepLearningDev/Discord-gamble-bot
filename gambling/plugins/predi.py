import json
import time
import hikari, crescent, miru

plugin = crescent.Plugin[hikari.GatewayBot, None]()

from gambling.client_instance import guild_id  # Ensure guild_id is an int
from gambling.points import get_points  # Import points functions if needed elsewhere

PREDICTIONS_FILE = "predictions.json"

def load_predictions() -> dict:
    try:
        with open(PREDICTIONS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": {}}

def save_predictions(data: dict) -> None:
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Global predictions data. We initialize it here.
predictions_data = load_predictions()

@plugin.include
@crescent.command(
    name="predi",
    description="Host a prediction event with an optional minimum gamble",
    guild=guild_id
)
class Predi:
    prediction: str = crescent.option(str, "Describe your prediction event")
    min_gamble: int = crescent.option(int, "Minimum amount to gamble with", default=0)

    async def callback(self, ctx: crescent.Context) -> None:
        user_id = str(ctx.interaction.user.id)
        # Reload current predictions from file.
        current_predictions = load_predictions()
        # Count how many active predictions this user (host) already has.
        active_count = sum(
            1 for event in current_predictions.get("active", {}).values()
            if event.get("host") == user_id
        )
        if active_count >= 5:
            await ctx.respond(
                "❌ You already have 5 active prediction events. Please determine the outcome of one before creating another.",
                flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Build a cool, formatted prediction event message.
        content = (
            "🎯 **New Prediction Event Launched!** 🎯\n\n"
            f"**Prediction:** *{self.prediction.capitalize()}?*\n"
            f"**Minimum Gamble:** {self.min_gamble} points\n\n"
            "Cast your vote below:"
        )
        # Create a Miru view with Yes and No buttons.
        view = miru.View(timeout=180)
        view.add_item(
            miru.Button(
                style=hikari.ButtonStyle.PRIMARY,
                label="Yes",
                custom_id="predi_yes"
            )
        )
        view.add_item(
            miru.Button(
                style=hikari.ButtonStyle.DANGER,
                label="No",
                custom_id="predi_no"
            )
        )
        # Send the prediction event.
        await ctx.respond(content, components=view.build())
        message = await ctx.interaction.fetch_initial_response()
        msg_id = str(message.id)
        # Add the new prediction event including the host's ID and a timestamp.
        current_predictions["active"][msg_id] = {
            "prediction": self.prediction,
            "min_gamble": self.min_gamble,
            "votes": {},  # Format: {user_id: {"vote": "YES"/"NO", "bet": <amount>}}
            "host": user_id,
            "timestamp": time.time()
        }
        save_predictions(current_predictions)
        global predictions_data
        predictions_data = current_predictions

@plugin.include
@crescent.event
async def on_component_interaction(event: hikari.InteractionCreateEvent) -> None:
    # Process button interactions for prediction events.
    if not isinstance(event.interaction, hikari.ComponentInteraction):
        return
    if event.interaction.custom_id not in ["predi_yes", "predi_no"]:
        return

    vote = "YES" if event.interaction.custom_id == "predi_yes" else "NO"
    msg_id = str(event.interaction.message.id)
    # Create a modal prompt for entering the bet amount using Miru.
    modal_custom_id = f"predi_bet_{vote}_{msg_id}"
    modal = miru.Modal(title="Enter your bet amount", custom_id=modal_custom_id)
    modal.add_item(
        miru.TextInput(
            label="Bet amount",
            custom_id="bet_amount",
            style=hikari.TextInputStyle.SHORT,
            required=True,
            placeholder="Enter a number"
        )
    )
    await event.interaction.create_modal_response(modal.title, modal.custom_id, components=modal.build())

@plugin.include
@crescent.event
async def on_modal_submit(event: hikari.InteractionCreateEvent) -> None:
    if event.interaction.type != hikari.InteractionType.MODAL_SUBMIT:
        return
    custom_id = event.interaction.custom_id
    if not custom_id.startswith("predi_bet_"):
        return
    try:
        _, _, vote, msg_id = custom_id.split("_", 3)
    except Exception:
        return

    # Extract the bet amount by iterating over the submitted components.
    bet_amount = None
    for action_row in event.interaction.components:
        for comp in action_row.components:
            if comp.custom_id == "bet_amount":
                bet_amount = comp.value
                break
        if bet_amount is not None:
            break
    if bet_amount is None:
        return

    user_id = str(event.interaction.user.id)
    # Convert bet amount to integer and validate.
    try:
        bet_value = int(bet_amount)
    except ValueError:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content="Invalid bet amount.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    # Check that the prediction event exists.
    if msg_id not in predictions_data["active"]:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content="Prediction event not found.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    # Prevent duplicate voting.
    if user_id in predictions_data["active"][msg_id]["votes"]:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content="You have already voted!",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    # Prevent the host from voting on their own prediction.
    if user_id == predictions_data["active"][msg_id].get("host"):
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content="You cannot vote on your own prediction event.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    # Check that the user has enough points to cover the bet.
    available_points = get_points(int(user_id))
    if bet_value > available_points:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content="You do not have enough points to place that bet.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    # Check if the bet meets the minimum gamble requirement.
    event_data = predictions_data["active"][msg_id]
    min_gamble = event_data.get("min_gamble", 0)
    if bet_value < min_gamble:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content=f"You must bet at least {min_gamble} points.",
            flags=hikari.MessageFlag.EPHEMERAL
        )
        return

    predictions_data["active"][msg_id]["votes"][user_id] = {
        "vote": vote,
        "bet": bet_amount
    }
    save_predictions(predictions_data)
    # Calculate how many people have voted so far.
    vote_count = len(predictions_data["active"][msg_id]["votes"])
    await event.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        content=f"Your bet of {bet_amount} for {vote} has been recorded!\nTotal votes: {vote_count}",
        flags=hikari.MessageFlag.EPHEMERAL
    )
