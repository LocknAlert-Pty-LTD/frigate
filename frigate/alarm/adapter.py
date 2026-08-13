"""Translates Frigate detections into canonical AlarmEvents.

This is the only place that knows about Frigate-specific detection fields
(camera, zone, label, score, false_positive). The alarm state machine
(frigate/alarm/engine.py) never sees a Frigate detection directly, only the
AlarmEvent this adapter produces, and this adapter never sees the state
machine at all: callers own the flow from detection -> adapter.evaluate() ->
(optional) engine.trigger().

Evaluation order, per zone: zone configured and armed in the current mode ->
not a false positive -> object type permitted -> confidence threshold ->
persistence/verification. "Alarm enabled" globally is a gate the caller
applies before ever constructing/using an adapter, not something checked
here. Entry/exit delay is also the caller's responsibility: this adapter
returns whether a detection qualifies, and the resolved ZoneAlarmRule (via
get_rule) carries the entry_delay_seconds to pass to the state machine's
trigger().
"""

from frigate.alarm.event import AlarmEvent
from frigate.alarm.rules import ZoneAlarmRule
from frigate.alarm.state import ArmedMode


class DetectionAlarmAdapter:
    """Evaluates Frigate detections against per-zone alarm rules.

    Verification is a single numeric threshold (verification_seconds): 0
    means instant-trigger, >0 means the object must remain qualified in the
    zone for that many seconds. This covers both verification modes required
    today; a future distinct strategy (e.g. multi-frame voting) would replace
    this check without changing the adapter's public interface.
    """

    def __init__(self, rules: dict[tuple[str, str], ZoneAlarmRule]) -> None:
        self._rules = rules
        self._pending: dict[tuple[str, str, str], float] = {}

    def get_rule(self, camera: str, zone: str) -> ZoneAlarmRule | None:
        return self._rules.get((camera, zone))

    def clear_object(self, camera: str, zone: str, object_id: str) -> None:
        """Drop persistence tracking, e.g. when an object leaves the zone or
        its tracked-object lifecycle ends."""
        self._pending.pop((camera, zone, object_id), None)

    def evaluate(
        self,
        *,
        camera: str,
        zone: str,
        object_id: str,
        label: str,
        score: float,
        timestamp: float,
        armed_mode: ArmedMode | None,
        false_positive: bool = False,
    ) -> AlarmEvent | None:
        """Return a qualifying AlarmEvent, or None if this detection doesn't
        qualify."""
        if armed_mode is None:
            return None

        rule = self._rules.get((camera, zone))
        if rule is None or not rule.enabled or armed_mode not in rule.arm_modes:
            return None

        if false_positive:
            return None

        if label not in rule.objects:
            return None

        if score < rule.min_confidence:
            return None

        key = (camera, zone, object_id)
        if rule.verification_seconds <= 0:
            self._pending.pop(key, None)
        else:
            first_seen = self._pending.setdefault(key, timestamp)
            if timestamp - first_seen < rule.verification_seconds:
                return None
            del self._pending[key]

        return AlarmEvent(
            event_type=rule.object_event_overrides.get(label, rule.event_type),
            camera_id=camera,
            timestamp=timestamp,
            zone_id=zone,
            object_type=label,
            confidence=score,
        )
