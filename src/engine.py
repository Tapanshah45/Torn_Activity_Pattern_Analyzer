from typing import Generator

from src.streamer import stream_campaign_members
from src.classifier import InactivityClassifier
from src.models import PlayerProfile


class CampaignAnalyzerEngine:
    """
    Thin orchestration layer that wires the streamer and classifier together.

    Usage:
        engine = CampaignAnalyzerEngine("campaign_21.json")
        for profile in engine.run():
            print(profile.name, profile.inferred_timezone)
    """

    def __init__(self, file_path: str, min_sleep_gap: float = 4.0):
        self.file_path = file_path
        self.classifier = InactivityClassifier(min_gap_hours=min_sleep_gap)

    def run(self) -> Generator[PlayerProfile, None, None]:
        """
        Stream members one at a time, classify each, and yield a PlayerProfile.
        Members with no snapshot data are silently skipped.
        """
        for member_raw in stream_campaign_members(self.file_path):
            result = self.classifier.analyze_member(member_raw)
            if result.get("status") != "no_data":
                yield PlayerProfile(**result)
