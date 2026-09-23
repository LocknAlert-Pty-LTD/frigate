"""Persisted history of qualifying alarm-triggered detections.

Distinct from AlarmSystem's own in-memory recent_events()/GET /alarm/events
(most-recent-100, lost on restart, for live display) and from
AlarmAuditLog/record_alarm_audit() (operator actions -- arm/disarm/clear/
bypass, not detections). This is the historical, restart-surviving,
false-alarm-annotatable counterpart used by the health dashboard's
false-alarm rate.

Needs frigate.models, but like audit.py that alone doesn't pull in
frigate.config's cv2 chain, so this module needs no exemption in
test_alarm_no_mqtt_dependency.py. AlarmSystem itself stays free of any DB
dependency by design; this lives entirely in the wiring layer
(frigate/app.py's _on_alarm_event), not in frigate/alarm/system.py.
"""

from datetime import UTC, datetime

from frigate.alarm.event import AlarmEvent
from frigate.models import AlarmEventLog


def record_alarm_event_log(event: AlarmEvent) -> None:
    AlarmEventLog.create(
        # Naive UTC, not datetime.now(UTC) -- see audit.py for why: peewee's
        # DateTimeField only parses a handful of naive formats back out of
        # sqlite, and a tz-aware value's "+00:00" suffix matches none of them.
        timestamp=datetime.now(UTC).replace(tzinfo=None),
        event_type=event.event_type.value,
        camera=event.camera_id,
        zone=event.zone_id,
        object_type=event.object_type,
        confidence=event.confidence,
        source=event.source,
        message=event.message,
        object_id=event.object_id,
    )
