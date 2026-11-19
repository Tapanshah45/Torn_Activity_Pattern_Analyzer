import pytest
from src.stats import calculate_circular_mean, format_hour_to_time, infer_timezone


class TestCircularMean:
    def test_midnight_crossing_mean(self):
        """23:00 and 01:00 should average to ~00:00, not 12:00."""
        hours = [23.0, 1.0]
        mean_h = calculate_circular_mean(hours)
        assert round(mean_h) % 24 == 0

    def test_standard_mean(self):
        """14:00 and 16:00 should average to 15:00."""
        hours = [14.0, 16.0]
        mean_h = calculate_circular_mean(hours)
        assert round(mean_h) == 15

    def test_single_value_returns_itself(self):
        assert round(calculate_circular_mean([7.5]), 1) == 7.5

    def test_empty_list_returns_zero(self):
        assert calculate_circular_mean([]) == 0.0

    def test_symmetric_around_noon(self):
        """10:00 and 14:00 should average to 12:00."""
        mean_h = calculate_circular_mean([10.0, 14.0])
        assert round(mean_h) == 12

    def test_four_values_crossing_midnight(self):
        """22:00, 23:00, 01:00, 02:00 → mean should be near midnight."""
        mean_h = calculate_circular_mean([22.0, 23.0, 1.0, 2.0])
        # midnight ± 30 minutes
        assert mean_h >= 23.5 or mean_h <= 0.5


class TestFormatHour:
    def test_half_hour(self):
        assert format_hour_to_time(23.5) == "23:30"

    def test_midnight(self):
        assert format_hour_to_time(0.0) == "00:00"

    def test_noon(self):
        assert format_hour_to_time(12.0) == "12:00"

    def test_rollover_on_59_minutes(self):
        # 23 hours + 59.5 minutes rounds minute to 60 → should roll to 00:00
        result = format_hour_to_time(23.0 + 59.5 / 60.0)
        assert result == "00:00"

    def test_wrap_above_24(self):
        assert format_hour_to_time(25.0) == "01:00"


class TestTimezoneInference:
    def test_utc_player(self):
        # midpoint at 03:30 → offset 0
        assert infer_timezone(3.5) == "UTC+0"

    def test_positive_offset(self):
        # midpoint at 01:30 UTC → offset +2
        assert infer_timezone(1.5) == "UTC+2"

    def test_negative_offset(self):
        # midpoint at 07:30 UTC → offset -4
        assert infer_timezone(7.5) == "UTC-4"
