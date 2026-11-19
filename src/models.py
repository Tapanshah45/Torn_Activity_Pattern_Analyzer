from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class SnapshotModel(BaseModel):
    captured_at: datetime
    online_status: str
    last_action_timestamp: Optional[int] = None
    last_action_relative: Optional[str] = None
    current_status: Optional[str] = None
    current_state: str


class MemberModel(BaseModel):
    player_id: int
    name: str
    level: int
    position: str
    snapshots: List[SnapshotModel]


class InactivityBlock(BaseModel):
    block_type: str
    start_utc: str
    end_utc: str
    duration_hours: float
    context: str


class PlayerProfile(BaseModel):
    player_id: int
    name: str
    total_snapshots: int
    estimated_sleep_window_utc: str
    avg_sleep_duration_hours: float
    inferred_timezone: str
    peak_active_hours_utc: List[int]
    primary_sleep_cycles: List[InactivityBlock]
    secondary_afk_blocks: List[InactivityBlock]
