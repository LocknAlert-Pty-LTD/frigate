"""Per-camera alarm zone configuration."""

from pydantic import Field

from frigate.alarm.event import AlarmEventType
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import ArmedMode

from ..base import FrigateBaseModel

__all__ = ["AlarmZoneConfig", "CameraAlarmConfig"]


class AlarmZoneConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=True,
        title="Enable alarm zone",
        description="Enable or disable this zone as an alarm trigger.",
    )
    objects: list[str] = Field(
        default_factory=list,
        title="Tracked objects",
        description="Object labels that are permitted to trigger this alarm zone. Must be a subset of objects -> track for this camera.",
    )
    event: AlarmEventType = Field(
        default=AlarmEventType.burglary,
        title="Alarm event type",
        description="The canonical alarm event type reported when this zone triggers.",
    )
    object_event_overrides: dict[str, AlarmEventType] = Field(
        default_factory=dict,
        title="Per-object event overrides",
        description="Override the alarm event type for specific object labels, e.g. reporting vehicles differently than people.",
    )
    min_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        title="Minimum confidence",
        description="Minimum detection confidence required for an object to qualify as an alarm trigger in this zone.",
    )
    verification_seconds: float = Field(
        default=0.0,
        ge=0.0,
        title="Verification time",
        description="Seconds a qualifying object must persist in the zone before triggering. 0 triggers instantly, matching a traditional sensor.",
    )
    delay: int = Field(
        default=0,
        ge=0,
        title="Entry delay",
        description="Entry delay (seconds) applied when this zone triggers while the system is armed, giving time to disarm before an alarm is raised.",
    )
    arm_modes: list[ArmedMode] = Field(
        default_factory=lambda: [ArmedMode.away, ArmedMode.stay],
        title="Active arm modes",
        description="Which arm modes this zone is active in. Remove 'stay' for an interior zone that should only trigger when armed away.",
    )

    def to_rule(self, camera: str, zone: str) -> ZoneAlarmRule:
        """Build the plain-dataclass rule the detection adapter evaluates against."""
        return ZoneAlarmRule(
            camera=camera,
            zone=zone,
            enabled=self.enabled,
            objects=frozenset(self.objects),
            event_type=self.event,
            object_event_overrides=dict(self.object_event_overrides),
            min_confidence=self.min_confidence,
            verification_seconds=self.verification_seconds,
            entry_delay_seconds=self.delay,
            arm_modes=frozenset(self.arm_modes),
        )


class CameraAlarmConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable alarm",
        description="Enable or disable the alarm engine for this camera; requires alarm to also be enabled at the global level.",
    )
    zones: dict[str, AlarmZoneConfig] = Field(
        default_factory=dict,
        title="Alarm zones",
        description="Alarm zone settings keyed by the Frigate zone name defined under this camera's zones.",
    )

    def build_rules(self, camera: str) -> dict[tuple[str, str], ZoneAlarmRule]:
        """Build the rules the detection adapter should evaluate for this camera."""
        if not self.enabled:
            return {}
        return {
            (camera, zone_name): zone.to_rule(camera, zone_name)
            for zone_name, zone in self.zones.items()
            if zone.enabled
        }
