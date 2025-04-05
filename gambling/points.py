import os
import json

POINTS_FILE = "points.json"

def load_points() -> dict:
    if os.path.exists(POINTS_FILE):
        with open(POINTS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_points(points: dict) -> None:
    with open(POINTS_FILE, "w") as f:
        json.dump(points, f, indent=4)

def get_points(user_id: int) -> int:
    points = load_points()  # Always load fresh from disk.
    return points.get(str(user_id), 0)

def update_points(user_id: int, new_total: int) -> None:
    # Ensure the user's points never go negative.
    if new_total < 0:
        new_total = 0
    points = load_points()  # Reload the current points.
    points[str(user_id)] = new_total
    save_points(points)

def add_point(user_id: int) -> None:
    points = load_points()  # Reload current points.
    key = str(user_id)
    points[key] = points.get(key, 0) + 1
    save_points(points)
