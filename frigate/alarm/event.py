"""Canonical alarm event.

Protocol-independent shape produced by the detection adapter (and, in later
phases, by arm/disarm/fault sources) and consumed by the SIA/Contact ID
protocol adapters. Those adapters must never see a Frigate detection or
config object directly, only this.
"""

from dataclasses import dataclass
from enum import Enum


class AlarmEventType(str, Enum):
    burglary = "burglary"
    panic = "panic"
    tamper = "tamper"
    fault = "fault"
    restore = "restore"
    camera_failure = "camera_failure"
    communication_failure = "communication_failure"
    arm = "arm"
    disarm = "disarm"
    test = "test"
    supervision = "supervision"


@dataclass(frozen=True)
class AlarmEvent:
    event_type: AlarmEventType
    camera_id: str
    timestamp: float
    zone_id: str | None = None
    object_type: str | None = None
    confidence: float | None = None
    source: str = "detection"
    message: str | None = None
    # The Frigate tracked-object id, which becomes Event.id once persisted
    # (see frigate/events/maintainer.py) -- lets a downstream consumer
    # (e.g. frigate/alarm/trail.py) correlate this alarm event back to the
    # real detection it came from. None for non-detection events (arm/
    # disarm/fault/etc).
    object_id: str | None = None
