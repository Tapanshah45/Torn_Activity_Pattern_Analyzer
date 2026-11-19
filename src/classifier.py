from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Dict, Any, Tuple

from src.models import InactivityBlock
from src.stats import calculate_circular_mean, format_hour_to_time, infer_timezone

# Thresholds (in hours) used across classification logic
_MIN_SLEEP_HOURS = 4.5   # gap must be at least this long to be primary sleep
_MAX_SLEEP_HOURS = 13.0  # gaps longer than this are anomalies, not sleep
_ACTIVE_LANDING_WINDOW_SEC = 25 * 60   # 25 minutes


def parse_iso(ts_str: str) -> datetime:
    """Parse an ISO-8601 datetime string (with or without 'Z') to an aware UTC datetime."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(timezone.utc)


class InactivityClassifier:
    """
    Converts a raw member snapshot list into structured sleep and AFK blocks.

    Pipeline:
        1. extract_action_timeline  — de-duplicate identical action timestamps,
                                      inject landing checkpoints for flights.
        2. extract_gaps             — find consecutive pairs separated by ≥ min_gap_sec.
        3. partition_daily_blocks   — bucket by calendar day, designate the longest
                                      qualifying gap as primary sleep, rest as Work/AFK.
        4. analyze_member           — orchestrates 1-3 and computes summary stats.
    """

    def __init__(self, min_gap_hours: float = 4.0, max_sleep_hours: float = _MAX_SLEEP_HOURS):
        self.min_gap_sec = min_gap_hours * 3600
        self.max_sleep_sec = max_sleep_hours * 3600

    # ------------------------------------------------------------------
    # Step 1 — Action timeline reconstruction
    # ------------------------------------------------------------------

    def extract_action_timeline(self, snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build a deduplicated list of *meaningful* activity checkpoints.

        Rules:
        - A checkpoint is emitted whenever last_action_timestamp changes.
        - A checkpoint is also emitted on a Traveling → non-Traveling state
          transition to capture the landing even if no explicit user action fires.
        - Consecutive snapshots with the same action timestamp are collapsed into one.
        """
        timeline: List[Dict[str, Any]] = []
        prev_action_ts = None
        prev_state: str | None = None

        for snap in snapshots:
            captured_dt = parse_iso(snap["captured_at"])
            act_ts: int | None = snap.get("last_action_timestamp")
            state: str = snap.get("current_state", "Okay")
            status: str = snap.get("current_status", "")

            # Detect a flight landing: state was Traveling and is now something else
            state_changed = (
                prev_state is not None
                and prev_state == "Traveling"
                and state != "Traveling"
            )

            action_updated = act_ts is not None and act_ts != prev_action_ts

            if action_updated or state_changed:
                # Prefer the reported action timestamp; fall back to snapshot capture time
                effective_ts = act_ts if act_ts is not None else int(captured_dt.timestamp())
                timeline.append({
                    "action_time": datetime.fromtimestamp(effective_ts, tz=timezone.utc),
                    "action_ts": effective_ts,
                    "captured_at": captured_dt,
                    "state": state,
                    "status": status,
                    "is_landing": state_changed,
                })
                if action_updated:
                    prev_action_ts = act_ts

            prev_state = state

        return timeline

    # ------------------------------------------------------------------
    # Step 2 — Gap extraction with flight context annotation
    # ------------------------------------------------------------------

    def extract_gaps(self, timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify contiguous inactivity gaps (≥ min_gap_sec) between timeline events.

        Gaps that begin from a Traveling state or end at a landing event are tagged
        with flight context so downstream logic can apply sleep-landing rules.
        """
        gaps: List[Dict[str, Any]] = []

        for i in range(len(timeline) - 1):
            start = timeline[i]
            end = timeline[i + 1]
            gap_sec = end["action_ts"] - start["action_ts"]

            if gap_sec < self.min_gap_sec:
                continue

            duration_h = round(gap_sec / 3600.0, 2)

            # Annotate flight-related gaps
            if start.get("state") == "Traveling" or end.get("is_landing"):
                context = f"Post-flight ({end.get('state', 'Unknown')})"
            else:
                context = "Standard"

            gaps.append({
                "start_dt": start["action_time"],
                "end_dt": end["action_time"],
                "duration_hours": duration_h,
                "context": context,
            })

        return gaps

    # ------------------------------------------------------------------
    # Step 3 — Daily partitioning into sleep vs. Work/AFK
    # ------------------------------------------------------------------

    def partition_daily_blocks(
        self, gaps: List[Dict[str, Any]]
    ) -> Tuple[List[InactivityBlock], List[InactivityBlock]]:
        """
        Group gaps by the UTC calendar date on which they started, then
        within each day designate:
          - The longest gap (if ≤ max_sleep_hours) → Primary Sleep
          - All shorter gaps that still meet min_gap_sec → Work / AFK
        """
        daily_buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for g in gaps:
            day_key = g["start_dt"].strftime("%Y-%m-%d")
            daily_buckets[day_key].append(g)

        primary_sleep: List[InactivityBlock] = []
        secondary_afk: List[InactivityBlock] = []

        for _day, b_gaps in daily_buckets.items():
            sorted_gaps = sorted(b_gaps, key=lambda x: x["duration_hours"], reverse=True)
            longest = sorted_gaps[0]

            # Only claim as sleep if within plausible sleep-duration bounds
            if _MIN_SLEEP_HOURS <= longest["duration_hours"] <= (self.max_sleep_sec / 3600.0):
                primary_sleep.append(InactivityBlock(
                    block_type="Primary Sleep",
                    start_utc=longest["start_dt"].strftime("%Y-%m-%d %H:%M"),
                    end_utc=longest["end_dt"].strftime("%Y-%m-%d %H:%M"),
                    duration_hours=longest["duration_hours"],
                    context=longest["context"],
                ))

            # Everything else in the same day is secondary (Work / AFK)
            for secondary in sorted_gaps[1:]:
                secondary_afk.append(InactivityBlock(
                    block_type="Work / AFK",
                    start_utc=secondary["start_dt"].strftime("%Y-%m-%d %H:%M"),
                    end_utc=secondary["end_dt"].strftime("%Y-%m-%d %H:%M"),
                    duration_hours=secondary["duration_hours"],
                    context=secondary["context"],
                ))

        return primary_sleep, secondary_afk

    # ------------------------------------------------------------------
    # Step 4 — Full member analysis
    # ------------------------------------------------------------------

    def analyze_member(self, member_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrate the full analysis pipeline for a single faction member.

        Returns a dict compatible with PlayerProfile or {"status": "no_data"}.
        """
        snapshots = member_data.get("snapshots", [])
        if not snapshots:
            return {"status": "no_data"}

        timeline = self.extract_action_timeline(snapshots)
        gaps = self.extract_gaps(timeline)
        sleep_blocks, afk_blocks = self.partition_daily_blocks(gaps)

        if sleep_blocks:
            onset_hours = [
                datetime.strptime(b.start_utc, "%Y-%m-%d %H:%M").hour
                + datetime.strptime(b.start_utc, "%Y-%m-%d %H:%M").minute / 60.0
                for b in sleep_blocks
            ]
            durations = [b.duration_hours for b in sleep_blocks]

            mean_onset = calculate_circular_mean(onset_hours)
            mean_duration = sum(durations) / len(durations)
            mean_wakeup = (mean_onset + mean_duration) % 24.0

            sleep_window_str = (
                f"{format_hour_to_time(mean_onset)} - {format_hour_to_time(mean_wakeup)}"
            )
            midpoint = (mean_onset + mean_duration / 2.0) % 24.0
            tz_str = infer_timezone(midpoint)
        else:
            sleep_window_str = "Indeterminate"
            mean_duration = 0.0
            tz_str = "Unknown"

        # Peak active hours: top 40 % of hourly activity buckets
        hourly_activity: Dict[int, int] = defaultdict(int)
        for t in timeline:
            hourly_activity[t["action_time"].hour] += 1

        if hourly_activity:
            counts = sorted(hourly_activity.values())
            threshold_idx = int(len(counts) * 0.6)
            threshold = counts[threshold_idx] if threshold_idx < len(counts) else counts[-1]
            peak_hours = sorted(h for h, count in hourly_activity.items() if count >= max(1, threshold))
        else:
            peak_hours = []

        return {
            "player_id": member_data.get("player_id"),
            "name": member_data.get("name"),
            "total_snapshots": len(snapshots),
            "estimated_sleep_window_utc": sleep_window_str,
            "avg_sleep_duration_hours": round(mean_duration, 2),
            "inferred_timezone": tz_str,
            "peak_active_hours_utc": peak_hours,
            "primary_sleep_cycles": sleep_blocks,
            "secondary_afk_blocks": afk_blocks,
        }
