"""Per-zone alarm rules the detection adapter evaluates detections against.

These are plain dataclasses, not the Pydantic alarm config (added in a later
phase). The adapter only depends on this shape; whatever builds it from the
real config just needs to produce (or duck-type as) a ZoneAlarmRule.
"""

from dataclasses import dataclass, field

from frigate.alarm.event import AlarmEventType
from frigate.alarm.state import ArmedMode


@dataclass(frozen=True)
class ZoneAlarmRule:
    """Resolved alarm configuration for one Frigate camera/zone pair."""

    camera: str
    zone: str
    enabled: bool = True
    # Object labels allowed to trigger this zone. Empty means nothing
    # qualifies: a label must be explicitly listed, so e.g. animals are
    # ignored by default rather than needing an exclusion list.
    objects: frozenset[str] = frozenset()
    event_type: AlarmEventType = AlarmEventType.burglary
    # Per-label event type overrides, e.g. {"car": AlarmEventType.burglary}
    # to give vehicles a different classification than the zone's default.
    object_event_overrides: dict[str, AlarmEventType] = field(default_factory=dict)
    min_confidence: float = 0.0
    # Seconds a qualifying object must persist in the zone before it counts.
    # 0 means instant-trigger (classic sensor emulation).
    verification_seconds: float = 0.0
    # Entry delay to apply if this zone triggers while armed; the caller
    # (not this rule) is responsible for passing it to the state machine's
    # trigger().
    entry_delay_seconds: int = 0
    # Which arm modes this zone is active in, e.g. an interior zone that
    # should only trigger when armed away, not when armed home or night.
    # Defaults to all three (maximally armed; users narrow per zone).
    arm_modes: frozenset[ArmedMode] = frozenset(
        {ArmedMode.away, ArmedMode.home, ArmedMode.night}
    )
    # When set, a qualifying detection is not triggered immediately -- the
    # caller (AlarmDetectionThread) instead asks the GenAI description
    # provider to confirm it first. This rule doesn't perform the check
    # itself (see frigate/alarm/ai_verification.py); it just carries the
    # opt-in flag, the same way entry_delay_seconds carries a caller-applied
    # setting rather than being applied here.
    ai_verification: bool = False
