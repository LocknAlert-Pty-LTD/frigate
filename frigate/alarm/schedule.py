"""Time-based arm/disarm schedule entries the scheduler thread evaluates.

Plain dataclass, not the Pydantic alarm config -- mirrors rules.py's split
between the core shape and whatever builds it from real config.
"""

from dataclasses import dataclass

from frigate.alarm.state import ArmedMode


@dataclass(frozen=True)
class ScheduleEntry:
    """One scheduled arm/disarm action."""

    time: str  # "HH:MM", 24h
    mode: ArmedMode | None  # None means disarm
    # Days this entry applies on, 0=Monday..6=Sunday (datetime.weekday()).
    # Empty means every day.
    days: frozenset[int] = frozenset()
