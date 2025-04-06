import json
import time
from asyncio import gather

import hikari, crescent

plugin = crescent.Plugin[hikari.GatewayBot, None]()

from gambling.client_instance import guild_id  # Ensure guild_id is an int
from gambling.points import get_points, update_points

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

# Autocomplete callback for the prediction_id option.
async def predi_resolve_autocomplete(ctx: crescent.AutocompleteContext, option: hikari.AutocompleteInteractionOption) -> list[tuple[str, str]]:
    predictions = load_predictions()
    return [
        (
            f"ID: ..{msg_id[-4:]} | Prediction: {data['prediction'].capitalize()} (Votes: {len(data.get('votes', {}))})",
            msg_id
        )
        for msg_id, data in predictions.get("active", {}).items()
    ]

@plugin.include
@crescent.command(
    name="predi-outcome",
    description="Resolve a prediction and award winners double their bet.",
    guild=guild_id
)
class PrediOutcome:
    prediction_id: str = crescent.option(
        str,
        "Select a prediction event to resolve",
        autocomplete=predi_resolve_autocomplete
    )
    result: str = crescent.option(
        str,
        "Outcome",
        choices=[("YES", "YES"), ("NO", "NO")]
    )

    async def callback(self, ctx: crescent.Context) -> None:
        predictions = load_predictions()  # Reload to ensure up-to-date data.
        pred_id = self.prediction_id
        outcome = self.result  # "YES" or "NO"
        if pred_id not in predictions.get("active", {}):
            await ctx.respond("Prediction event not found.", flags=hikari.MessageFlag.EPHEMERAL)
            return

        event_data = predictions["active"].pop(pred_id)
        # Check that the prediction event has existed for at least 1 minutes.
        if time.time() - event_data.get("timestamp", 0) < 60:
            predictions["active"][pred_id] = event_data
            save_predictions(predictions)
            await ctx.respond("This prediction must be active for at least 1 minute before resolving.", flags=hikari.MessageFlag.EPHEMERAL)
            return
        save_predictions(predictions)

        # Fetch display names for each voter concurrently.
        user_ids = list(event_data["votes"].keys())
        members = await gather(*(ctx.rest.fetch_member(guild_id, int(uid)) for uid in user_ids))
        names = {str(member.user.id): member.display_name for member in members}

        # Build a nicely formatted results output.
        result_lines = []
        for user_id, vote_data in event_data["votes"].items():
            try:
                bet = int(vote_data["bet"])
            except Exception:
                bet = 0
            display = names.get(user_id, f"<@{user_id}>")
            if vote_data["vote"] == outcome:
                current = get_points(int(user_id))
                new_total = current + (bet * 2)
                update_points(int(user_id), new_total)
                result_lines.append(f"• **{display}** won **{bet * 2}** points (new total: **{new_total}**).")
            else:
                result_lines.append(f"• **{display}** lost their bet of **{bet}** points.")
        results_text = "\n".join(result_lines)
        result_message = (
            f"✨ **Prediction Resolved!** ✨\n\n"
            f"**Prediction:** *{event_data['prediction']}*\n"
            f"**Outcome:** **{outcome}**\n\n"
            f"**Winners/Losers:**\n{results_text}"
        )
        await ctx.respond(result_message)
