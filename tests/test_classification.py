from datetime import datetime, timezone
import pytest
from src.classifier import InactivityClassifier
from src.models import InactivityBlock


class TestDailyPartitioning:
    def setup_method(self):
        self.classifier = InactivityClassifier(min_gap_hours=4.0)

    def _make_gap(self, start_h: int, end_h: int, date: str = "2026-09-29") -> dict:
        """Helper: build a gap dict for a single calendar day."""
        start = datetime.fromisoformat(f"{date}T{start_h:02d}:00:00+00:00")
        end_date = date
        if end_h <= start_h:
            # Crosses midnight — bump date by one day
            from datetime import timedelta
            d = datetime.fromisoformat(f"{date}T00:00:00+00:00") + timedelta(days=1)
            end_date = d.strftime("%Y-%m-%d")
        end = datetime.fromisoformat(f"{end_date}T{end_h:02d}:00:00+00:00")
        duration = (end - start).total_seconds() / 3600.0
        return {
            "start_dt": start,
            "end_dt": end,
            "duration_hours": round(duration, 2),
            "context": "Standard",
        }

    def test_longest_becomes_primary_sleep(self):
        gaps = [
            self._make_gap(13, 17, "2026-09-29"),   # 4.0 h  → AFK (13:00–17:00)
            self._make_gap(23, 6,  "2026-09-29"),   # 7.0 h  → Sleep (23:00–06:00)
        ]
        sleep, afk = self.classifier.partition_daily_blocks(gaps)
        assert len(sleep) == 1
        assert sleep[0].duration_hours == 7.0
        assert sleep[0].block_type == "Primary Sleep"
        assert len(afk) == 1
        assert afk[0].duration_hours == 4.0
        assert afk[0].block_type == "Work / AFK"

    def test_gap_above_max_sleep_is_not_primary(self):
        """A 14-hour gap exceeds the 13-hour ceiling and should not be primary sleep."""
        gaps = [self._make_gap(0, 14, "2026-09-29")]   # 14 h
        sleep, afk = self.classifier.partition_daily_blocks(gaps)
        assert len(sleep) == 0

    def test_gap_below_min_sleep_is_not_primary(self):
        """A 4.0-hour gap is below the 4.5 h floor for primary sleep."""
        gaps = [self._make_gap(1, 5, "2026-09-29")]    # exactly 4 h
        sleep, afk = self.classifier.partition_daily_blocks(gaps)
        assert len(sleep) == 0

    def test_two_days_produce_two_sleep_blocks(self):
        gaps = [
            self._make_gap(23, 6, "2026-09-29"),
            self._make_gap(23, 6, "2026-09-30"),
        ]
        sleep, afk = self.classifier.partition_daily_blocks(gaps)
        assert len(sleep) == 2

    def test_empty_gaps_returns_empty_lists(self):
        sleep, afk = self.classifier.partition_daily_blocks([])
        assert sleep == []
        assert afk == []


class TestActionTimeline:
    def setup_method(self):
        self.classifier = InactivityClassifier()

    def _snap(self, captured_at: str, act_ts: int | None, state: str = "Okay", status: str = "") -> dict:
        return {
            "captured_at": captured_at,
            "online_status": "Offline",
            "last_action_timestamp": act_ts,
            "last_action_relative": "1 hour ago",
            "current_status": status,
            "current_state": state,
        }

    def test_deduplicates_identical_timestamps(self):
        snaps = [
            self._snap("2026-09-29T10:00:00+00:00", 1000),
            self._snap("2026-09-29T10:05:00+00:00", 1000),  # same → skip
            self._snap("2026-09-29T10:10:00+00:00", 2000),  # new action
        ]
        timeline = self.classifier.extract_action_timeline(snaps)
        assert len(timeline) == 2

    def test_landing_checkpoint_emitted(self):
        snaps = [
            self._snap("2026-09-29T08:00:00+00:00", 500, state="Traveling", status="Traveling to Cayman Islands"),
            self._snap("2026-09-29T10:00:00+00:00", 500, state="Abroad",    status="In Cayman Islands"),
        ]
        timeline = self.classifier.extract_action_timeline(snaps)
        # Second snap has same act_ts but different state → landing checkpoint
        assert any(t["is_landing"] for t in timeline)

    def test_no_snapshots_returns_empty_timeline(self):
        assert self.classifier.extract_action_timeline([]) == []


class TestFullMemberAnalysis:
    def setup_method(self):
        self.classifier = InactivityClassifier(min_gap_hours=4.0)

    def test_no_data_returns_status(self):
        result = self.classifier.analyze_member({"player_id": 1, "name": "Ghost", "snapshots": []})
        assert result == {"status": "no_data"}

    def test_basic_profile_fields(self):
        """Single sleep gap should produce a valid profile dict."""
        snaps = []
        base_ts = 1727600000   # arbitrary epoch anchor

        # Simulate: active at T=0, then offline for 7 hours, then active again
        for offset, ts_delta in [(0, 0), (7 * 3600 + 60, 7 * 3600)]:
            from datetime import datetime, timezone, timedelta
            cap = datetime.fromtimestamp(base_ts + offset, tz=timezone.utc).isoformat()
            snaps.append({
                "captured_at": cap,
                "online_status": "Online" if offset == 0 else "Offline",
                "last_action_timestamp": base_ts + ts_delta,
                "last_action_relative": "just now",
                "current_status": "Okay",
                "current_state": "Okay",
            })

        member = {"player_id": 99, "name": "TestPlayer", "level": 10, "position": "Member", "snapshots": snaps}
        result = self.classifier.analyze_member(member)
        assert result["player_id"] == 99
        assert "estimated_sleep_window_utc" in result
        assert isinstance(result["peak_active_hours_utc"], list)
