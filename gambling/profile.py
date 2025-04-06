import os
import json

PROFILE_FILE = "profiles.json"

def load_profiles() -> dict:
    """Load profiles from the JSON file."""
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_profiles(profiles: dict) -> None:
    """Save profiles to the JSON file."""
    with open(PROFILE_FILE, "w") as f:
        json.dump(profiles, f, indent=4)

def get_profile(user_id: int) -> dict:
    """
    Retrieve the profile for a user. If the profile doesn't exist,
    create a new profile with default values.
    """
    profiles = load_profiles()
    uid = str(user_id)
    if uid not in profiles:
        # Create a new profile with default values.
        profiles[uid] = {
            "user_id": uid,
            "title": "",            # Your custom title (e.g., "Champion")
            "color": 0,             # Store color as an integer (e.g., 0x1E90FF)
            "points": 0,            # Starting points
            "wins_blackjack": 0,    # Blackjack wins
            "wins_predi": 0,        # Prediction wins
            "achievements": [],     # List to store achievement names
            "inventory": []         # List for items you might add later
        }
        save_profiles(profiles)
    return profiles[uid]

def update_profile(user_id: int, profile: dict) -> None:
    """Update the profile for a user and save the profiles."""
    profiles = load_profiles()
    profiles[str(user_id)] = profile
    save_profiles(profiles)
