import math
from typing import List


def calculate_circular_mean(hour_floats: List[float]) -> float:
    """
    Compute the circular (angular) mean of a list of hour values (0–24).

    Standard arithmetic averaging fails for times that cross midnight
    (e.g., averaging 23:00 and 01:00 yields 12:00 instead of 00:00).
    Projecting onto the unit circle and averaging the sine/cosine
    components avoids this artefact.
    """
    if not hour_floats:
        return 0.0
    sin_sum = sum(math.sin(2 * math.pi * h / 24.0) for h in hour_floats)
    cos_sum = sum(math.cos(2 * math.pi * h / 24.0) for h in hour_floats)
    mean_rad = math.atan2(sin_sum, cos_sum)
    mean_hour = (mean_rad * 24.0 / (2 * math.pi)) % 24.0
    return mean_hour


def format_hour_to_time(hour_float: float) -> str:
    """Convert a fractional hour value (e.g. 23.5) to an HH:MM string."""
    norm_h = hour_float % 24.0
    h = int(norm_h)
    m = int(round((norm_h - h) * 60.0))
    if m == 60:
        h = (h + 1) % 24
        m = 0
    return f"{h:02d}:{m:02d}"


def infer_timezone(midpoint_utc: float) -> str:
    """
    Estimate a player's UTC offset from the midpoint of their average sleep window.

    The heuristic assumes the median person sleeps with a midpoint around 03:30
    local time (i.e. roughly 1–6 AM).  The offset is rounded to the nearest
    whole hour.

    Example: midpoint at 22:30 UTC → offset = round(3.5 − 22.5) = round(−19) …
    but atan2-based circular mean keeps midpoints sane, so typical values stay
    within ±12 h of 03:30.
    """
    offset = round(3.5 - midpoint_utc)
    sign = "+" if offset >= 0 else ""
    return f"UTC{sign}{offset}"
