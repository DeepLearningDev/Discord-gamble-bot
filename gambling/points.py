import os
import json

PROFILE_FILE = "profiles.json"

def load_profiles() -> dict:
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_profiles(profiles: dict) -> None:
    with open(PROFILE_FILE, "w") as f:
        json.dump(profiles, f, indent=4)

def get_profile(user_id: int) -> dict:
    """
    Retrieve the user's profile. If it doesn't exist, create one with default values.
    """
    profiles = load_profiles()
    uid = str(user_id)
    if uid not in profiles:
        profiles[uid] = {
            "user_id": uid,
            "points": 0,
            "wins_blackjack": 0,
            "wins_predi": 0,
            "inventory": []
        }
        save_profiles(profiles)
    return profiles[uid]

def update_profile(user_id: int, profile: dict) -> None:
    profiles = load_profiles()
    profiles[str(user_id)] = profile
    save_profiles(profiles)

def get_points(user_id: int) -> int:
    """
    Retrieve the user's points from their profile.
    """
    profile = get_profile(user_id)
    return profile.get("points", 0)

def update_points(user_id: int, new_total: int) -> None:
    """
    Update the user's points in their profile. Ensures that points never go negative.
    """
    profile = get_profile(user_id)
    profile["points"] = new_total if new_total >= 0 else 0
    update_profile(user_id, profile)

def add_point(user_id: int) -> None:
    """
    Increment the user's points by one.
    """
    profile = get_profile(user_id)
    profile["points"] = profile.get("points", 0) + 1
    update_profile(user_id, profile)
